from .constants import MeasurementType, DeviceType, SampleRateSetting
from .parser import Parser
from .callbacks import Callbacks
from .settings import StreamSettings
from .commands import Commands

from collections import deque
import asyncio
import bleak


class CallbacksImpl(Callbacks):
    def __init__(self, callback=None):
        self._callback = callback

        self.ppg_queue = deque()
        self.acc_queue = deque()

    def _update_one(self) -> bool:
        if not self.ppg_queue or not self.acc_queue:
            return False

        if self.acc_queue[0]['ts'] < self.ppg_queue[0]['ts']:
            self.acc_queue.popleft()
            return True

        acc_front = self.acc_queue[0]
        ax = acc_front['ax']
        ay = acc_front['ay']
        az = acc_front['az']

        ppg_front = self.ppg_queue[0]
        ts = ppg_front['ts']
        ppg0 = ppg_front['ppg0']
        ppg1 = ppg_front['ppg1']
        ppg2 = ppg_front['ppg2']
        self.ppg_queue.popleft()

        if self._callback:
            result = {'ppg0': ppg0, 'ppg1': ppg1, 'ppg2': ppg2, 'ax': ax, 'ay': ay, 'az': az}
            self._callback(DeviceType.OH1.name, ts, result)

        return True

    def _update(self):
        while self._update_one():
            pass

    def on_measurement(self, type: MeasurementType, payload):
        measurement_type = MeasurementType(type)
        ts = int(payload[0] / 1000) / 1000

        if MeasurementType.PPG == measurement_type:
            ambient = payload[4]
            ppg0 = payload[1] - ambient
            ppg1 = payload[2] - ambient
            ppg2 = payload[3] - ambient

            self.ppg_queue.append(
                {"ts": ts, "ppg0": ppg0, "ppg1": ppg1, "ppg2": ppg2})

            self._update()

        if MeasurementType.ACC == measurement_type:
            x = payload[1] / 1000
            y = payload[2] / 1000
            z = payload[3] / 1000

            d = {"ts": ts, 'ax': x, 'ay': y, 'az': z}

            self.acc_queue.append(d)

            self._update()


class Device:
    def __init__(self, type: DeviceType, address: str, control_handle: int,
                 data_handle: int, callback=None):
        self._type = type
        self._addr = address
        self._control_handle = control_handle
        self._data_handle = data_handle
        self._control_ccc_handle = control_handle + 1
        self._data_ccc_handle = data_handle + 1
        self.stream_settings = StreamSettings()
        self._callbacks = CallbacksImpl(callback=callback)

        self._parser = Parser(stream_settings=self.stream_settings, callbacks=self._callbacks)

        if DeviceType.H10 == type:
            self.stream_settings.ACC_sample_rate = SampleRateSetting.SampleRate200
            self.stream_settings.ECG_sample_rate = SampleRateSetting.SampleRate200

        if DeviceType.OH1 == type:
            self.stream_settings.ACC_sample_rate = SampleRateSetting.SampleRate50
            self.stream_settings.PPG_sample_rate = SampleRateSetting.SampleRate135

    async def connect(self) -> bool:
        self._ble = bleak.BleakClient(self._addr)
        await self._ble.connect()

        await self._ble.write_gatt_char(self._control_ccc_handle, bytearray([0x02, 0x00]))
        await self._ble.write_gatt_char(self._data_ccc_handle, bytearray([0x01, 0x00]))
        await self._ble.write_gatt_descriptor(self._control_handle, bytearray([0x02, 0x00]))
        await self._ble.write_gatt_descriptor(self._data_handle, bytearray([0x01, 0x00]))
        await self._ble.write_gatt_char(self._control_handle, bytearray([0x01]))
        await self._ble.set_disconnected_callback(self._parser.parse)

        return True

    async def send_command(self, command: bytearray):
        result = await self._ble.write_gatt_char(self._control_handle, command)
        return self._parser.parse(result)

    async def start(self) -> bool:
        if not await self.connect():
            return False

        await self.send_command(Commands.GetACCSettings)
        await self.send_command(Commands.GetPPGSettings)

        await self.send_command(Commands.OH1StartPPG)
        await self.send_command(Commands.OH1StartACC)

        return True

    async def run(self):
        async with self._ble:
            while True:
                data = await self._ble.read_gatt_char(self._data_handle)
                self._parser.parse(data)


class OH1(Device):
    def __init__(self, address: str, control_handle: int,
                 data_handle: int, callback=None):
        super().__init__(DeviceType.OH1, address=address,
                         control_handle=control_handle,
                         data_handle=data_handle,
                         callback=callback)

    async def run(self):
        await super().run()