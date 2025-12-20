from datetime import datetime


class TimeUtil:

    @staticmethod
    def formatted_now_with_ms():
        # Get current time
        now = datetime.now()

        # Format time string, ensure milliseconds are 3 digits
        formatted_time = now.strftime('%Y-%m-%d %H:%M:%S')

        milliseconds = now.microsecond // 1000
        formatted_time_with_milliseconds = formatted_time + f".{milliseconds:03}"

        return formatted_time_with_milliseconds
