"""원본 CSV에 새 날짜를 더해 검증하고, 갱신 사본을 교체한다."""

import csv
import hashlib
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from time import sleep

from csv_population_repository import CsvPopulationRepository
from seoul_population_api import SeoulPopulationApi


KST = timezone(timedelta(hours=9))


class PopulationRefresh:
    def __init__(self, seed: CsvPopulationRepository, cache_dir: Path, api: SeoulPopulationApi):
        self.seed = seed
        self.api = api
        self.regions = dict(seed.list_districts(include_seoul_total=True))
        if len(self.regions) != api.REGIONS or seed.SEOUL_TOTAL_CODE not in self.regions:
            raise ValueError("자동 갱신은 서울시 합계와 25개 자치구를 포함한 원본 CSV가 필요합니다.")
        self.seed_start, self.seed_end = seed.get_date_range()
        self.seed_count = seed.get_data_quality()["record_count"]
        # 다른 CSV를 지정하거나 팀 원본을 교체하면 이전 사본을 섞지 않는다.
        digest = hashlib.sha256(seed.file_path.read_bytes()).hexdigest()
        self.cache = cache_dir / f"population-{digest}.csv"

    def load_latest(self) -> CsvPopulationRepository:
        repository = CsvPopulationRepository(self.cache, require_indicators=True)
        try:
            count = repository.load()
        except FileNotFoundError:
            return self.seed
        start, end = repository.get_date_range()
        if (start != self.seed_start or end < self.seed_end or count < self.seed_count
                or dict(repository.list_districts(include_seoul_total=True)) != self.regions):
            raise ValueError("갱신 CSV가 원본의 기간·자치구와 일치하지 않습니다.")
        return repository

    def refresh_once(self, today=None):
        """자료가 준비된 날짜만 추가한다. 다운로드나 검증 오류 시 사본을 교체하지 않는다."""
        today = today or datetime.now(KST).date()
        cutoff = today - timedelta(days=4)
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        # 여러 서버가 같은 폴더를 사용하더라도 동시에 이전 파일 위에 쓰지 않는다.
        with self.cache.with_suffix(".lock").open("a+b") as lock:
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

            current = self.load_latest()
            _, last = current.get_date_range()
            quality = current.get_data_quality()
            gaps = {datetime.fromisoformat(day).date()
                    for days in quality["missing_dates_by_district"].values() for day in days}
            pending = {day for day in gaps if self.seed_end < day <= cutoff}
            pending.update(last + timedelta(days=i) for i in range(1, (cutoff - last).days + 1))

            rows, skipped = [], []
            for day in sorted(pending):
                batch = self.api.fetch_day(day)
                regions = {row["시구코드"].strip(): row["시구명"].strip() for row in batch}
                if len(batch) != len(regions) or any(self.regions.get(code) != name
                                                     for code, name in regions.items()):
                    raise ValueError(f"Open API 자치구 정보가 원본과 다릅니다 ({day}).")
                if regions == self.regions:
                    rows.extend(batch)
                else:
                    skipped.append(day)

            repository = self._append(current, rows, quality["encoding_used"]) if rows else current
            return repository, len(rows) // self.api.REGIONS, skipped

    def _append(self, current, rows, encoding):
        with current.file_path.open(encoding=encoding, newline="") as source:
            headers = [column.strip() for column in next(csv.reader(source))]
        if not set(headers) <= set(self.api.COLUMNS.values()):
            raise ValueError("자동 갱신에 필요한 원본 CSV 열 이름을 확인해 주세요.")
        with NamedTemporaryFile(dir=self.cache.parent, suffix=".tmp", delete=False) as temporary:
            path = Path(temporary.name)
        try:
            shutil.copyfile(current.file_path, path)
            with path.open("rb") as copied:
                copied.seek(-1, os.SEEK_END)
                needs_newline = copied.read(1) not in (b"\r", b"\n")
            with path.open("a", encoding=encoding, newline="") as destination:
                if needs_newline:
                    destination.write("\r\n")
                csv.DictWriter(destination, fieldnames=headers, extrasaction="ignore").writerows(rows)
                destination.flush()
                os.fsync(destination.fileno())

            repository = CsvPopulationRepository(path, require_indicators=True)
            repository.load()
            path.replace(self.cache)
            repository.file_path = self.cache
            return repository
        finally:
            path.unlink(missing_ok=True)

    def run(self, publish, logger):
        """서버 시작 직후와 이후 매일 한국 시간 정오에 동기화한다."""
        while True:
            retry = False
            try:
                repository, added_days, skipped = self.refresh_once()
                publish(repository)
                logger.info("생활인구 갱신 확인. 추가 %d일, 최신 %s",
                            added_days, repository.get_date_range()[1])
                if skipped:
                    logger.warning("아직 26개 지역이 준비되지 않은 날짜 %d일. 다음 갱신 때 재확인합니다.", len(skipped))
            except (OSError, ValueError) as error:
                retry = True
                logger.warning("생활인구 갱신 실패. 기존 데이터로 계속 조회합니다. %s", error)
            now = datetime.now(KST)
            noon = now.replace(hour=12, minute=0, second=0, microsecond=0)
            next_check = noon if now < noon else noon + timedelta(days=1)
            wait_seconds = (next_check - now).total_seconds()
            sleep(min(wait_seconds, 3600) if retry else wait_seconds)
