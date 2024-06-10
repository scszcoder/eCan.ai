from datetime import datetime


class TimeUtil:

    @staticmethod
    def formatted_now_with_ms():
        # 获取当前时间
        now = datetime.now()

        # 格式化时间字符串，确保毫秒数为3位
        formatted_time = now.strftime('%Y-%m-%d %H:%M:%S')

        milliseconds = now.microsecond // 1000
        formatted_time_with_milliseconds = formatted_time + f".{milliseconds:03}"

        return formatted_time_with_milliseconds
