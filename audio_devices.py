from typing import Any

import pyaudiowpatch as pyaudio


def list_input_devices(selected_index: int | None = None) -> list[dict[str, Any]]:
    pa = pyaudio.PyAudio()
    devices: list[dict[str, Any]] = []
    default_index: int | None = None
    try:
        try:
            wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
            default_index = wasapi.get("defaultInputDevice")
        except Exception:
            try:
                default_index = pa.get_default_input_device_info().get("index")
            except Exception:
                default_index = None

        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            if int(info.get("maxInputChannels", 0)) <= 0:
                continue
            devices.append({
                "index": int(info["index"]),
                "name": str(info.get("name", f"Input {index}")),
                "host_api": int(info.get("hostApi", -1)),
                "default_sample_rate": int(float(info.get("defaultSampleRate", 0))),
                "max_input_channels": int(info.get("maxInputChannels", 0)),
                "is_default": default_index == int(info["index"]),
                "selected": selected_index == int(info["index"]),
            })
    finally:
        pa.terminate()
    return devices


def default_input_index() -> int | None:
    devices = list_input_devices()
    for device in devices:
        if device["is_default"]:
            return int(device["index"])
    return int(devices[0]["index"]) if devices else None


def input_device_exists(index: int | None) -> bool:
    if index is None:
        return False
    return any(device["index"] == index for device in list_input_devices(index))
