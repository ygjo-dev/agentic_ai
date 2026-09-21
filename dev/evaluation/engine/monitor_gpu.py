"""평가용 GPU 지원. 실행 하드웨어 기록과, 원하면 GPU 팬 소음 억제.

    environment()                     이 기계의 GPU 이름 · VRAM. Test Run 의 meta.environment 에 실림
    monitor = GpuMonitor()            발화와 발화 사이에서 팬을 보고 기다림 (before_case)

GPU 를 기록하는 까닭은 **실행 하드웨어의 재현성**이다 (어느 GPU · 몇 장 · VRAM). 온도 · 팬은 결과에
남기지 않는다. GpuMonitor 는 다음 발화를 부르기 전에 기다리거나 멈출 뿐이다. **판정에는 안 섞인다.**
재는 시간(timing.resolve_s)은 resolve 호출 하나만 감싸므로 기다려도 안 늘어난다. 기다린 시간의
합은 run_evaluation 이 meta.fan_wait_s 에 적는다.

팬 소음 억제(fan_quiet)가 켜져 있으면 다음 발화 앞에서 GPU 전부의 fan.speed 를 본다.
하나라도 FAN_PAUSE_AT 이상이면 모두 FAN_RESUME_AT 이하가 될 때까지 FAN_POLL_S 마다 다시 보고,
되면 바로 부른다. 부르는 중인 Resolve 는 팬 때문에 끊지 않는다. 꺼져 있으면 nvidia-smi 를 안 부른다.

장비 보호는 드라이버가 알리는 열 제한(clocks_event_reasons 의 hw · sw thermal slowdown)만 본다.
켜져 있을 때 그것을 보면 StopRun 으로 평가를 멈춘다. 온도 문턱을 따로 두지 않는다.

nvidia-smi 가 없거나 fan.speed 를 읽을 수 없는 기계에서는 기다리지 않고 평가는 그대로 돈다.
팬 곡선 · 전력 한도 · 클럭을 바꾸지 않는다. 읽기만 한다.
"""

import subprocess
import time


class StopRun(Exception):
    """평가를 여기서 멈춘다. 까닭이 meta.stopped 에 남고 거기까지의 결과는 그대로 나감.

    monitor(GPU 열 제한)나 progress 가 던짐. 다른 예외는 삼키지 않음
    """

# nvidia-smi 에 묻는 칸. 차례가 sample 의 차례다.
QUERY = "index,name,fan.speed,clocks_event_reasons.hw_thermal_slowdown,clocks_event_reasons.sw_thermal_slowdown"

# 팬 소음 억제. fan.speed(%)는 GPU 전부 중 가장 높은 것.
FAN_PAUSE_AT = 46     # 다음 발화 앞에서 이 이상이면 기다림
FAN_RESUME_AT = 42    # 기다리다 모두 이 이하가 되면 바로 다음 발화
FAN_POLL_S = 1.0      # 기다리는 동안 팬을 다시 보는 간격(초)


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
    """GPU 마다 한 줄. [{index, name, fan, throttle}]. 못 읽으면 None.

    규칙  nvidia-smi 가 없거나 실패하거나 모양이 다르면 None. 평가를 멈추지 않음
          [N/A] 인 칸은 None. throttle 은 드라이버가 열 때문에 클럭을 내렸나(hw · sw)
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
        if len(parts) != 5:
            return None
        gpus.append({
            "index": _number(parts[0]),
            "name": parts[1],
            "fan": _number(parts[2]),
            "throttle": _flag(parts[3], parts[4]),
        })
    return gpus or None


def _peak_fan(gpus: list[dict] | None) -> int | None:
    """GPU 전부 중 가장 높은 fan.speed. 읽을 수 있는 GPU 가 없으면 None."""
    values = [gpu["fan"] for gpu in gpus or [] if gpu.get("fan") is not None]
    return max(values) if values else None


class GpuMonitor:
    """평가 한 번의 GPU 팬 소음 억제. 다음 발화 앞에서 팬을 보고 기다림.

    규칙  run_evaluation 이 발화마다 Resolve 를 부르기 바로 앞에서 before_case 를 부름.
          부르는 중에는 안 불림. 그래서 부르는 중인 Resolve 를 팬 때문에 끊는 일이 없음
          waiting 은 지금 팬 때문에 기다리는 중인가. 화면이 실행 상태 글자에 씀
          waited_s 는 이 monitor 가 팬 때문에 기다린 초의 합. 기다리다 StopRun 으로 멈춰도 거기까지 셈
    제약  GPU 설정을 바꾸지 않는다. 판정 · 결과 줄에 손대지 않는다. 온도 문턱을 두지 않는다
    """

    def __init__(self, *, sampler=sample, sleep=time.sleep, clock=time.monotonic):
        self._sampler, self._sleep, self._clock = sampler, sleep, clock
        self.waiting = False
        self.waited_s = 0.0

    def before_case(self, done: int, *, fan_quiet: bool, should_stop=None) -> float:
        """다음 발화를 불러도 되나 보고 필요하면 기다림. 기다린 초.

        입력  done 은 이 평가에서 끝난 발화 수(StopRun 문장에 씀). fan_quiet 는 이번 실행 구간의 팬 소음 억제
        규칙  fan_quiet 가 거짓이면 nvidia-smi 를 안 부르고 0
              GPU 전부의 fan.speed 중 가장 높은 것이 FAN_PAUSE_AT 이상이면 FAN_POLL_S 마다 다시 보고,
              모두 FAN_RESUME_AT 이하가 되면 바로 돌아감 (46 · 42 hysteresis)
              FAN_RESUME_AT 초과 · FAN_PAUSE_AT 미만이면 안 기다림
              못 읽거나(nvidia-smi 없음 · 실패) fan.speed 가 전부 [N/A] 면 안 기다림. 기다리다 못 읽게 돼도 그만 기다림
              기다리는 동안 should_stop() 이 참이면 그만 기다림. 멈추는 것은 부르는 쪽이 함
              본 샘플에 드라이버 열 제한이 있으면 StopRun
        제약  기다리는 상한을 두지 않는다. 사람은 「중지」로 멈춘다
        """
        if not fan_quiet:
            return 0.0
        gpus = self._check(done)
        peak = _peak_fan(gpus)
        if peak is None or peak < FAN_PAUSE_AT:
            return 0.0
        started = self._clock()
        self.waiting = True
        try:
            while peak is not None and peak > FAN_RESUME_AT:
                if should_stop and should_stop():
                    break
                self._sleep(FAN_POLL_S)
                peak = _peak_fan(self._check(done))
        finally:
            self.waiting = False
            waited = self._clock() - started
            self.waited_s += waited
        return waited

    def _check(self, done: int) -> list[dict] | None:
        """샘플 한 번. 드라이버 열 제한이 보이면 StopRun."""
        gpus = self._sampler()
        if gpus and any(gpu.get("throttle") for gpu in gpus):
            raise StopRun(f"GPU 열 제한 감지 ({done}건 뒤)")
        return gpus
