import asyncio
from polarpy import OH1

OH1_ADDR = "A0:9E:1A:6C:B1:DA"
OH1_CONTROL_ATTRIBUTE_HANDLE = 0x003f
OH1_DATA_ATTRIBUTE_HANDLE = 0x0042


def callback(type: str, timestamp: float, payload: dict):
    print(f'{timestamp} {payload}')


async def main():
    device = OH1(address=OH1_ADDR,
                 control_handle=OH1_CONTROL_ATTRIBUTE_HANDLE,
                 data_handle=OH1_DATA_ATTRIBUTE_HANDLE,
                 callback=callback)

    if await device.start():
        while True:
            await device.run()

asyncio.run(main())
