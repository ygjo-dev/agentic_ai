"""실행 하드웨어 기록과, 원하면 사무실 조용 정책의 쉼표.

    environment()                     이 기계의 GPU 이름 · VRAM. Test Run 의 meta.environment 에 실림
    monitor = GpuMonitor(gate=True)   조용 정책(아래 POLICY)으로 부르는 박자만 조절

GPU 를 기록하는 까닭은 **실행 하드웨어의 재현성**이다 (어느 GPU · 몇 장 · VRAM). 온도는 결과에
남기지 않는다. GpuMonitor 는 발화와 발화 사이에서 쉬거나 멈출 뿐이고 그 기록(summary)은 부르는
쪽이 원할 때만 읽는다 — runner 는 결과에 싣지 않는다. **판정에는 안 섞인다.** 재는 시간
(timing.resolve_s)은 resolve 호출 하나만 감싸므로 쉬어도 안 늘어난다.

nvidia-smi 가 없거나 읽을 수 없는 기계에서는 available 이 거짓인 한 벌만 남고 평가는 그대로 돈다.
팬 곡선 · 전력 한도 · 클럭을 바꾸지 않는다. 읽기만 한다.
"""

import datetime
import subprocess
import time
import zoneinfo

KST = zoneinfo.ZoneInfo("Asia/Seoul")

# nvidia-smi 에 묻는 칸. 차례가 _parse 의 차례다.
QUERY = (
    "index,name,utilization.gpu,temperature.gpu,fan.speed,"
    "clocks_event_reasons.hw_thermal_slowdown,clocks_event_reasons.sw_thermal_slowdown"
)

# 사무실 조용 정책. 온도는 GPU 넷 중 가장 뜨거운 것, 사용률도 가장 높은 것.
POLICY = {
    "start_max_util": 5,        # 이 이하로 한가해야 시작
    "start_max_temp": 58,       # 이 이하로 식어야 시작
    "every": 3,                 # 이만큼 부르고
    "sleep_s": 5.0,             # 이만큼 쉬고 온도를 봄
    "pause_at": 66,             # 이 이상이면 멈춤
    "resume_at": 58,            # 이 이하로 식으면 다시
    "end_cooldown_above": 62,   # 끝났을 때 이보다 뜨거우면 resume_at 까지 식힘
    "poll_s": 15.0,             # 기다리는 동안 온도를 보는 간격
    "max_wait_s": 1800.0,       # 한 번 기다리는 상한. 넘으면 시작은 그냥 가고, 멈춤은 평가를 멈춤
}


# 실행 하드웨어로 묻는 칸. 차례가 environment 의 차례다.
ENVIRONMENT_QUERY = "index,name,memory.total"


def environment() -> dict:
    """이 기계의 GPU. {available, gpus: [{index, name, memory_total_mib}]}.

    규칙  nvidia-smi 가 없거나 실패하거나 모양이 다르면 {available: False, gpus: []}. 평가를 멈추지 않음
          온도 · 사용률은 안 적음. 재현에 필요한 것은 무슨 GPU 가 몇 장 · VRAM 얼마인가임
    """
    try:
        done = subprocess.run(
            ["nvidia-smi", f"--query-gpu={ENVIRONMENT_QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "gpus": []}
    if done.returncode != 0:
        return {"available": False, "gpus": []}
    gpus = []
    for line in done.stdout.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            return {"available": False, "gpus": []}
        gpus.append({"index": _number(parts[0]), "name": parts[1], "memory_total_mib": _number(parts[2])})
    return {"available": bool(gpus), "gpus": gpus}


def _number(text: str) -> int | None:
    try:
        return int(float(text))
    except ValueError:
        return None


def _flag(*texts: str) -> bool | None:
    """열 제한 칸들을 하나로. 하나라도 Active 면 참. 읽을 수 없으면 None."""
    known = [text for text in texts if text in ("Active", "Not Active")]
    if not known:
        return None
    return any(text == "Active" for text in known)


def sample() -> list[dict] | None:
    """GPU 마다 한 줄. [{index, name, util, temp, fan, throttle}]. 못 읽으면 None.

    규칙  nvidia-smi 가 없거나 실패하거나 모양이 다르면 None. 평가를 멈추지 않음
          [N/A] 인 칸은 None. throttle 은 열 때문에 클럭을 내렸나(hw · sw)
    """
    try:
        done = subprocess.run(
            ["nvidia-smi", f"--query-gpu={QUERY}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    gpus = []
    for line in done.stdout.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 7:
            return None
        gpus.append({
            "index": _number(parts[0]),
            "name": parts[1],
            "util": _number(parts[2]),
            "temp": _number(parts[3]),
            "fan": _number(parts[4]),
            "throttle": _flag(parts[5], parts[6]),
        })
    return gpus or None


def _peak(gpus: list[dict], key: str) -> int | None:
    values = [gpu[key] for gpu in gpus if gpu.get(key) is not None]
    return max(values) if values else None


class GpuMonitor:
    """평가 한 번의 박자 조절. gate 면 조용 정책대로 쉬고 멈춤. 본 온도는 이 객체에만 남고 결과에는 안 실림.

    규칙  before_run · after_case · after_run 은 runner.run 이 부름
          기록은 샘플마다 {at, phase, done, temp, util, fan, throttle} 한 줄. 여럿이면 가장 높은 값
          gate 가 아니면 쉬지 않음. 샘플도 시작 · 끝 · every 마다만 떠서 박자가 안 바뀜
          gate 면 열 제한을 보는 순간 식히고 runner.StopRun 으로 평가를 멈춤
    제약  GPU 설정을 바꾸지 않는다. 판정 · 결과 줄에 손대지 않는다
    """

    def __init__(self, *, gate: bool = False, policy: dict | None = None, sampler=sample, sleep=time.sleep, clock=time.monotonic):
        self.gate = gate
        self.policy = {**POLICY, **(policy or {})}
        self._sampler, self._sleep, self._clock = sampler, sleep, clock
        self.log: list[dict] = []
        self.gpus: list[dict] = []
        self.available = False
        self.pauses = 0
        self.pause_seconds = 0.0
        self.throttled: bool | None = None
        self.notes: list[str] = []

    def _take(self, phase: str, done: int) -> dict | None:
        gpus = self._sampler()
        if not gpus:
            return None
        self.available = True
        if not self.gpus:
            self.gpus = [{"index": gpu["index"], "name": gpu["name"]} for gpu in gpus]
        flags = [gpu["throttle"] for gpu in gpus if gpu["throttle"] is not None]
        throttle = any(flags) if flags else None
        if throttle is not None:
            self.throttled = bool(self.throttled) or throttle
        entry = {
            "at": datetime.datetime.now(KST).isoformat(timespec="seconds"),
            "phase": phase,
            "done": done,
            "temp": _peak(gpus, "temp"),
            "util": _peak(gpus, "util"),
            "fan": _peak(gpus, "fan"),
            "throttle": throttle,
        }
        self.log.append(entry)
        return entry

    def _wait(self, phase: str, done: int, ready) -> bool:
        """ready(샘플)이 참이 될 때까지 poll_s 마다 봄. max_wait_s 를 넘으면 거짓."""
        started = self._clock()
        while True:
            entry = self._take(phase, done)
            if entry is None or ready(entry):
                return True
            if self._clock() - started >= self.policy["max_wait_s"]:
                return False
            self._sleep(self.policy["poll_s"])

    def before_run(self) -> None:
        entry = self._take("start", 0)
        if not self.gate or entry is None:
            return
        policy = self.policy
        if entry["util"] is not None and entry["util"] <= policy["start_max_util"] and entry["temp"] is not None \
                and entry["temp"] <= policy["start_max_temp"]:
            return
        self._sleep(policy["poll_s"])
        if not self._wait("start_wait", 0, lambda e: (e["util"] or 0) <= policy["start_max_util"]
                          and (e["temp"] or 0) <= policy["start_max_temp"]):
            self.notes.append("시작 조건을 기다리다 상한을 넘겨 그대로 시작함")

    def after_case(self, done: int, planned: int) -> None:
        policy = self.policy
        if done >= planned or done % policy["every"]:
            return
        if self.gate:
            self._sleep(policy["sleep_s"])
        entry = self._take("during", done)
        if not self.gate or entry is None:
            return
        if entry["throttle"]:
            from dev.evaluation import runner

            self._wait("throttle_cooldown", done, lambda e: (e["temp"] or 0) <= policy["resume_at"])
            raise runner.StopRun(f"GPU 열 제한 감지 ({done}/{planned} 뒤)")
        if entry["temp"] is not None and entry["temp"] >= policy["pause_at"]:
            self.pauses += 1
            started = self._clock()
            self._sleep(policy["poll_s"])
            cooled = self._wait("pause", done, lambda e: (e["temp"] or 0) <= policy["resume_at"])
            self.pause_seconds += self._clock() - started
            if not cooled:
                from dev.evaluation import runner

                raise runner.StopRun(f"GPU 가 {policy['max_wait_s']:.0f}초 안에 식지 않음 ({done}/{planned} 뒤)")

    def after_run(self, done: int) -> None:
        entry = self._take("end", done)
        if not self.gate or entry is None or entry["temp"] is None:
            return
        if entry["temp"] > self.policy["end_cooldown_above"]:
            self._sleep(self.policy["poll_s"])
            self._wait("cooldown", done, lambda e: (e["temp"] or 0) <= self.policy["resume_at"])

    def summary(self) -> dict:
        """이 monitor 가 본 것 한 벌. runner 는 결과에 싣지 않음 (부르는 쪽이 원할 때 읽음).

        출력  {available, gpus, start_temp, max_temp, end_temp, max_util, max_fan, pauses,
               pause_seconds, thermal_throttle, samples, gate, policy, notes, log}
               end_temp 는 평가가 끝난 순간(식히기 전)의 온도. thermal_throttle 은 못 읽으면 None
        """
        temps = [entry["temp"] for entry in self.log if entry["temp"] is not None]
        ends = [entry for entry in self.log if entry["phase"] == "end"]
        starts = [entry for entry in self.log if entry["phase"] == "start"]
        return {
            "available": self.available,
            "gpus": self.gpus,
            "start_temp": starts[0]["temp"] if starts else None,
            "max_temp": max(temps) if temps else None,
            "end_temp": ends[-1]["temp"] if ends else None,
            "max_util": _peak(self.log, "util"),
            "max_fan": _peak(self.log, "fan"),
            "pauses": self.pauses,
            "pause_seconds": round(self.pause_seconds, 1),
            "thermal_throttle": self.throttled,
            "samples": len(self.log),
            "gate": self.gate,
            "policy": dict(self.policy) if self.gate else None,
            "notes": list(self.notes),
            "log": list(self.log),
        }
