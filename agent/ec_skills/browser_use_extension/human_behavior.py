"""
Human Behavior Simulation Module
================================
Simulates realistic human-like mouse movements, typing, and other behaviors
to avoid detection by anti-bot systems, especially on e-commerce platforms.

Features:
- Bezier curve-based mouse trajectory generation with overshoot & tremor
- Human-like typing with variable speed and occasional errors
- Scroll simulation with inertia and reading-pause patterns
- Click hesitation, delays, and random position offset (bot always clicks center)
- Preset configs: DEFAULT_CONFIG, ECOMMERCE_STEALTH_CONFIG, FAST_RELAXED_CONFIG

Market data sources: pydoll (autoscrape-labs), Browserbase Stealth, Hyperbrowser,
smooth-cursor-playwright, Ghost Cursor research.

Author: eCan.ai
"""

import time
import random
import math
from typing import Tuple, Optional, List
from dataclasses import dataclass, field
from enum import Enum

from utils.logger_helper import logger_helper as logger


class TypingMode(Enum):
    """Typing simulation mode"""
    RANDOM = "random"           # Random character delay
    REALISTIC = "realistic"     # Based on QWERTY keyboard layout
    FAST = "fast"              # Faster than average user
    SLOW = "slow"              # Slower than average user


@dataclass
class HumanBehaviorConfig:
    """Configuration for human behavior simulation.

    Defaults are tuned for e-commerce platform anti-detection (Taobao/JD/Tmall/
    Amazon/etc.) where speed is secondary to not being flagged.
    """

    # Mouse movement settings
    # Market standard for e-commerce: 0.5–2.5s total move time depending on distance.
    # Fitts's Law: MT = a + b × log₂(D/W + 1), humans take longer for small/far targets.
    # Key anti-detection signals: perfect straight lines, constant velocity, instant teleport.
    mouse_move_duration_min: float = 0.5   # Minimum time for mouse movement (seconds)
    mouse_move_duration_max: float = 2.0   # Maximum time for mouse movement (seconds)
    mouse_bezier_segments: int = 6         # Number of bezier curve segments (market: 5–8)
    mouse_wobble_enabled: bool = True      # Add small random wobbles to trajectory
    mouse_overshoot_probability: float = 0.7   # ~70% chance of overshooting fast moves
    mouse_overshoot_pixels: float = 8.0       # 3–12px overshoot range (market data)
    mouse_tremor_std: float = 1.0            # Gaussian noise σ ≈ 1px (physiological tremor)

    # Click settings
    # Market standard for e-commerce: 150–500ms hesitation before click, 200–600ms after.
    # Key: never click at exact element center — bots always click center, humans vary.
    click_pre_hesitation_min: float = 0.15  # Min hesitation before click (seconds)
    click_pre_hesitation_max: float = 0.6   # Max hesitation before click (seconds)
    click_post_delay_min: float = 0.2       # Min delay after click (seconds)
    click_post_delay_max: float = 0.6       # Max delay after click (seconds)
    double_click_interval: float = 0.3       # Interval between double-click
    click_offset_max: float = 10.0          # Max random offset from element center (px)

    # Typing settings
    # Market standard for e-commerce: 50–300ms/char depending on QWERTY row.
    # Home row (asdfghjkl) faster, number row ~30% slower, special chars ~40% slower.
    # ~2% typo rate with auto-correction is indistinguishable from real users.
    typing_mode: TypingMode = TypingMode.REALISTIC
    char_delay_min: float = 0.05           # Min delay between characters (seconds) [market: 50–150ms]
    char_delay_max: float = 0.25           # Max delay between characters (seconds) [market: 100–300ms]
    word_delay_min: float = 0.3            # Min delay between words (seconds) [market: 300–800ms]
    word_delay_max: float = 0.8            # Max delay between words (seconds) [market: 800–2000ms]
    error_rate: float = 0.02               # Probability of typing error (0-1) [market: ~2%]
    backspace_rate: float = 0.5            # Probability of correcting error with backspace [market: 40–60%]
    error_correction_delay: float = 0.4    # Delay before correcting error (seconds)

    # Scroll settings
    # Market standard for e-commerce: scroll in chunks with variable delays.
    # Human-like scroll includes: momentum, friction, jitter, micro-pauses, overshoot.
    scroll_chunk_size: int = 4             # Number of scroll units per chunk [market: 3–5]
    scroll_chunk_delay_min: float = 0.3    # Min delay between scroll chunks [market: 300–600ms]
    scroll_chunk_delay_max: float = 0.8   # Max delay between scroll chunks [market: 600–1500ms]
    scroll_inertia_enabled: bool = True    # Add deceleration at end of scroll
    scroll_read_pause_min: float = 2.0     # Min pause when "reading" content (seconds)
    scroll_read_pause_max: float = 5.0     # Max pause when "reading" content (seconds)

    # Hover settings
    # Market standard: 100–800ms hover before triggering tooltips/dropdowns.
    hover_pre_delay_min: float = 0.1       # Min delay before hover (seconds)
    hover_pre_delay_max: float = 0.4      # Max delay before hover (seconds)
    hover_post_delay_min: float = 0.15    # Min delay after hover (seconds)
    hover_post_delay_max: float = 0.5      # Max delay after hover (seconds)

    # Idle/fatigue simulation (mimics human session degradation over time)
    idle_action_probability: float = 0.1   # Probability of idle micro-action per step
    fatigue_factor: float = 1.15           # Slow-down multiplier applied per session hour


# Default configuration instance — tuned for e-commerce anti-detection.
DEFAULT_CONFIG = HumanBehaviorConfig()


# Preset: Aggressive e-commerce stealth (Taobao/JD/Tmall/Amazon/SHEIN/etc.)
# Prioritizes evasion over speed. Use when anti-bot detection is triggered.
ECOMMERCE_STEALTH_CONFIG = HumanBehaviorConfig(
    mouse_move_duration_min=0.8,
    mouse_move_duration_max=2.5,
    mouse_bezier_segments=8,
    mouse_overshoot_probability=0.7,
    mouse_overshoot_pixels=10.0,
    mouse_tremor_std=1.2,
    click_pre_hesitation_min=0.2,
    click_pre_hesitation_max=0.8,
    click_post_delay_min=0.3,
    click_post_delay_max=0.8,
    click_offset_max=12.0,
    char_delay_min=0.08,
    char_delay_max=0.3,
    word_delay_min=0.4,
    word_delay_max=1.2,
    scroll_chunk_delay_min=0.4,
    scroll_chunk_delay_max=1.0,
    scroll_read_pause_min=2.5,
    scroll_read_pause_max=5.0,
    hover_pre_delay_min=0.2,
    hover_pre_delay_max=0.6,
    fatigue_factor=1.2,
)


# Preset: Fast/relaxed stealth (general sites, low-risk scenarios)
# Balances speed and evasion. Use for non-e-commerce or trusted environments.
FAST_RELAXED_CONFIG = HumanBehaviorConfig(
    mouse_move_duration_min=0.2,
    mouse_move_duration_max=0.8,
    mouse_bezier_segments=4,
    mouse_overshoot_probability=0.3,
    mouse_overshoot_pixels=5.0,
    char_delay_min=0.03,
    char_delay_max=0.1,
    word_delay_min=0.1,
    word_delay_max=0.3,
    scroll_chunk_delay_min=0.1,
    scroll_chunk_delay_max=0.3,
    click_pre_hesitation_min=0.05,
    click_pre_hesitation_max=0.2,
    error_rate=0.0,
    fatigue_factor=1.0,
)


class HumanMouseSimulator:
    """
    Generates human-like mouse movements using Bezier curves.
    """

    def __init__(self, config: Optional[HumanBehaviorConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self._last_position = (0, 0)

    def set_last_position(self, x: int, y: int):
        """Set the last known mouse position"""
        self._last_position = (x, y)

    def get_last_position(self) -> Tuple[int, int]:
        """Get the last known mouse position"""
        return self._last_position

    def _bezier_curve(self, points: List[Tuple[float, float]], t: float) -> Tuple[float, float]:
        """
        Calculate point on a Bezier curve.

        Args:
            points: Control points [(x, y), ...]
            t: Parameter 0-1

        Returns:
            (x, y) coordinate on curve
        """
        n = len(points) - 1
        x = sum(math.comb(n, i) * (1 - t) ** (n - i) * t ** i * points[i][0]
                for i in range(n + 1))
        y = sum(math.comb(n, i) * (1 - t) ** (n - i) * t ** i * points[i][1]
                for i in range(n + 1))
        return (x, y)

    def _generate_control_points(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float]
    ) -> List[Tuple[float, float]]:
        """
        Generate Bezier control points for natural movement.

        Human mouse movements typically:
        - Start and end with deceleration
        - Have slight overshoot in perpendicular direction (~70% chance, 3–12px)
        - Use curved paths, not straight lines
        - Physiological tremor: Gaussian noise σ ≈ 1px scaled inversely with velocity
        """
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.sqrt(dx ** 2 + dy ** 2)

        # Perpendicular offset for natural curve
        if distance > 50:
            perp_offset = random.uniform(-distance * 0.15, distance * 0.15)
        else:
            perp_offset = random.uniform(-10, 10)

        # Calculate perpendicular direction
        if abs(dx) > abs(dy):
            perp_x = -dy / distance * perp_offset
            perp_y = dx / distance * perp_offset
        else:
            perp_x = dy / distance * perp_offset
            perp_y = -dx / distance * perp_offset

        # Overshoot handling: ~70% chance of overshooting fast movements
        overshoot_x, overshoot_y = 0.0, 0.0
        if distance > 80 and random.random() < self.config.mouse_overshoot_probability:
            overshoot_pixels = random.uniform(
                -self.config.mouse_overshoot_pixels,
                self.config.mouse_overshoot_pixels
            )
            if distance > 0:
                overshoot_x = dx / distance * overshoot_pixels
                overshoot_y = dy / distance * overshoot_pixels

        # Generate control points
        control_points = [start]

        # Add intermediate points with curve
        mid_x = (start[0] + end[0]) / 2 + perp_x + overshoot_x
        mid_y = (start[1] + end[1]) / 2 + perp_y + overshoot_y

        if self.config.mouse_wobble_enabled and distance > 100:
            wobble_x = random.uniform(-distance * 0.1, distance * 0.1)
            wobble_y = random.uniform(-distance * 0.1, distance * 0.1)
            mid_x += wobble_x
            mid_y += wobble_y

        control_points.append((mid_x, mid_y))

        # Final point: overshoot overshoots past target, then we correct
        if distance > 80 and random.random() < self.config.mouse_overshoot_probability:
            control_points.append((end[0] + overshoot_x, end[1] + overshoot_y))
            control_points.append(end)  # correct back
        else:
            control_points.append(end)

        return control_points

    def generate_trajectory(
        self,
        start: Tuple[float, float],
        end: Tuple[float, float],
        num_points: int = 30
    ) -> List[Tuple[int, int]]:
        """
        Generate a natural-looking mouse trajectory.

        Uses minimum-jerk velocity profile: slow start, peak at mid-path, slow end.
        Adds physiological tremor scaled inversely with velocity.

        Args:
            start: Starting position (x, y)
            end: Ending position (x, y)
            num_points: Number of points in trajectory

        Returns:
            List of (x, y) coordinates forming the path
        """
        control_points = self._generate_control_points(start, end)

        trajectory = []
        for i in range(num_points):
            t = i / (num_points - 1)

            # Apply minimum-jerk easing (slow start/end, peak in middle)
            if t < 0.5:
                eased_t = 4 * t * t * t
            else:
                eased_t = 1 - pow(-2 * t + 2, 3) / 2

            point = self._bezier_curve(control_points, eased_t)

            # Physiological tremor: Gaussian noise inversely scaled with velocity
            # At endpoints velocity is low → more tremor; at middle velocity is high → less
            velocity_factor = abs(math.sin(math.pi * t))  # 0 at ends, 1 at middle
            tremor = random.gauss(0, self.config.mouse_tremor_std / max(velocity_factor, 0.3))

            x = int(point[0] + tremor)
            y = int(point[1] + tremor)
            trajectory.append((x, y))

        return trajectory

    def move_to(
        self,
        target_x: int,
        target_y: int,
        pyautogui_module,
        duration: Optional[float] = None
    ):
        """
        Move mouse to target with human-like trajectory.

        Args:
            target_x: Target X coordinate
            target_y: Target Y coordinate
            pyautogui_module: The pyautogui module to use
            duration: Override duration (uses config if not provided)
        """
        import pyautogui

        start = self._last_position
        target = (target_x, target_y)

        # Skip if already at target
        if abs(start[0] - target[0]) < 5 and abs(start[1] - target[1]) < 5:
            return

        # Generate trajectory
        trajectory = self.generate_trajectory(start, target)

        # Calculate duration based on distance if not provided
        if duration is None:
            distance = math.sqrt((target[0] - start[0]) ** 2 + (target[1] - start[1]) ** 2)
            duration = random.uniform(
                self.config.mouse_move_duration_min,
                self.config.mouse_move_duration_max
            )
            # Scale duration with distance (longer distance = longer time)
            duration = duration * (1 + distance / 1000)

        # Move through trajectory with easing
        num_points = len(trajectory)
        point_duration = duration / num_points

        for i, (x, y) in enumerate(trajectory):
            pyautogui_module.moveTo(x, y)
            self._last_position = (x, y)

            # Add micro-pause at key points (start, middle, end)
            if i == 0 or i == num_points // 2 or i == num_points - 1:
                time.sleep(point_duration * 0.5)
            else:
                time.sleep(point_duration)

    def click(
        self,
        x: int,
        y: int,
        pyautogui_module,
        clicks: int = 1,
        hesitation: bool = True,
        apply_offset: bool = True
    ):
        """
        Perform click with hesitation, delay, and random offset.

        Key anti-detection: bots always click at exact element center.
        Real humans vary click position by ±click_offset_max pixels.

        Args:
            x: Target X coordinate (element center)
            y: Target Y coordinate (element center)
            pyautogui_module: The pyautogui module to use
            clicks: Number of clicks
            hesitation: Whether to add pre-click hesitation
            apply_offset: Apply random offset from center (anti-detection)
        """
        # Random offset from element center — real humans don't click at exact center
        if apply_offset:
            offset_x = random.uniform(-self.config.click_offset_max, self.config.click_offset_max)
            offset_y = random.uniform(-self.config.click_offset_max, self.config.click_offset_max)
            x = int(x + offset_x)
            y = int(y + offset_y)

        # Move to target first
        self.move_to(x, y, pyautogui_module)

        # Pre-click hesitation (simulates decision making)
        if hesitation:
            hesitation_time = random.uniform(
                self.config.click_pre_hesitation_min,
                self.config.click_pre_hesitation_max
            )
            time.sleep(hesitation_time)

        # Perform click(s)
        if clicks == 1:
            pyautogui_module.click()
        elif clicks == 2:
            pyautogui_module.click(clicks=2, interval=self.config.double_click_interval)
        else:
            pyautogui_module.click(clicks=clicks)

        # Post-click delay
        post_delay = random.uniform(
            self.config.click_post_delay_min,
            self.config.click_post_delay_max
        )
        time.sleep(post_delay)

    def hover(self, x: int, y: int, pyautogui_module):
        """
        Perform hover with pre and post delays.
        """
        # Pre-hover delay
        pre_delay = random.uniform(
            self.config.hover_pre_delay_min,
            self.config.hover_pre_delay_max
        )
        time.sleep(pre_delay)

        # Move to target
        self.move_to(x, y, pyautogui_module)

        # Post-hover delay
        post_delay = random.uniform(
            self.config.hover_post_delay_min,
            self.config.hover_post_delay_max
        )
        time.sleep(post_delay)


class HumanTypingSimulator:
    """
    Generates human-like typing patterns.
    """

    # QWERTY keyboard row distances (approximate)
    KEYBOARD_ROWS = {
        'q': 0, 'w': 1, 'e': 2, 'r': 3, 't': 4, 'y': 5, 'u': 6, 'i': 7, 'o': 8, 'p': 9,
        'a': 0, 's': 1, 'd': 2, 'f': 3, 'g': 4, 'h': 5, 'j': 6, 'k': 7, 'l': 8,
        'z': 0, 'x': 1, 'c': 2, 'v': 3, 'b': 4, 'n': 5, 'm': 6
    }

    def __init__(self, config: Optional[HumanBehaviorConfig] = None):
        self.config = config or DEFAULT_CONFIG

    def _get_char_delay(self, char: str, prev_char: Optional[str] = None) -> float:
        """
        Calculate delay for typing a character.
        Takes into account keyboard layout for realistic typing.
        """
        char_lower = char.lower()

        # Base delay from config
        base_delay = random.uniform(
            self.config.char_delay_min,
            self.config.char_delay_max
        )

        # Adjust for typing mode
        if self.config.typing_mode == TypingMode.FAST:
            base_delay *= 0.5
        elif self.config.typing_mode == TypingMode.SLOW:
            base_delay *= 1.5

        # Home row bonus (faster for home row keys)
        if char_lower in self.KEYBOARD_ROWS:
            row = self.KEYBOARD_ROWS[char_lower]
            if row <= 1:  # Top two rows are "home row adjacent"
                base_delay *= 0.8

        # Number row is slower
        if char_lower.isdigit():
            base_delay *= 1.3

        # Special characters
        if char in '!@#$%^&*()':
            base_delay *= 1.4  # Shift combinations are slower
        elif char in '-=_+[]{}|;:\'\",.<>/?':
            base_delay *= 1.2

        # Word boundary bonus
        if prev_char == ' ':
            base_delay *= 1.2

        return base_delay

    def _should_correct_error(self) -> bool:
        """Determine if an error should be corrected"""
        return random.random() < self.config.backspace_rate

    def type_text(self, text: str, pyautogui_module, correct_errors: bool = True) -> List[str]:
        """
        Type text with human-like timing and occasional errors.

        Args:
            text: Text to type
            pyautogui_module: The pyautogui module to use
            correct_errors: Whether to simulate error correction

        Returns:
            List of actions taken (for logging/debugging)
        """
        actions = []
        prev_char = None

        for i, char in enumerate(text):
            # Check for typing error
            should_error = correct_errors and random.random() < self.config.error_rate

            if should_error:
                # Generate wrong character (similar looking or adjacent key)
                wrong_char = self._get_adjacent_char(char)
                pyautogui_module.press(wrong_char)
                actions.append(f"error: pressed '{wrong_char}' instead of '{char}'")

                # Delay before realizing error
                time.sleep(self.config.error_correction_delay)

                # Correct with backspace
                if self._should_correct_error():
                    pyautogui_module.press('backspace')
                    actions.append("corrected: backspace")

                    # Type correct character
                    delay = self._get_char_delay(char, prev_char)
                    time.sleep(delay)
                    pyautogui_module.press(char)
                    actions.append(f"typed: '{char}'")

                    prev_char = char
                    continue

            # Normal typing
            delay = self._get_char_delay(char, prev_char)
            time.sleep(delay)

            # Handle special characters
            if char == ' ':
                pyautogui_module.press('space')
                actions.append("typed: space")

                # Word gap delay
                word_delay = random.uniform(
                    self.config.word_delay_min,
                    self.config.word_delay_max
                )
                time.sleep(word_delay)

            elif char == '\n':
                pyautogui_module.press('enter')
                actions.append("typed: enter")

            elif char == '\t':
                pyautogui_module.press('tab')
                actions.append("typed: tab")

            elif char.isupper() or char in '!@#$%^&*()_+{}|:"<>?':
                # Hold shift for uppercase or special chars
                with pyautogui_module.hold('shift'):
                    pyautogui_module.press(char.lower())
                actions.append(f"typed: '{char}' (shift)")

            else:
                pyautogui_module.press(char)
                actions.append(f"typed: '{char}'")

            prev_char = char

        return actions

    def _get_adjacent_char(self, char: str) -> str:
        """
        Get an adjacent character on QWERTY keyboard.
        Used to simulate typing errors.
        """
        adjacent_map = {
            'a': 'sq', 'b': 'vn', 'c': 'xv', 'd': 'sf', 'e': 'wr',
            'f': 'dg', 'g': 'fh', 'h': 'gj', 'i': 'uo', 'j': 'hk',
            'k': 'jl', 'l': 'ko', 'm': 'n', 'n': 'bm', 'o': 'ip',
            'p': 'o', 'q': 'wa', 'r': 'et', 's': 'ad', 't': 'ry',
            'u': 'yi', 'v': 'cb', 'w': 'qe', 'x': 'zc', 'y': 'tu',
            'z': 'x', '1': '2', '2': '13', '3': '24', '4': '35',
            '5': '46', '6': '57', '7': '68', '8': '79', '9': '80', '0': '9'
        }

        char_lower = char.lower()
        if char_lower in adjacent_map:
            adjacent = adjacent_map[char_lower]
            return random.choice(adjacent)
        return char_lower


class HumanScrollSimulator:
    """
    Generates human-like scrolling behavior.
    """

    def __init__(self, config: Optional[HumanBehaviorConfig] = None):
        self.config = config or DEFAULT_CONFIG

    def scroll(
        self,
        amount: int,
        pyautogui_module,
        direction: str = "down",
        read_pause: bool = False
    ):
        """
        Perform scroll with human-like behavior.

        Human-like scroll includes: chunked scroll, variable delays, inertia at end,
        optional reading pauses, and overshoot correction.

        Args:
            amount: Number of scroll units (positive = down, negative = up)
            pyautogui_module: The pyautogui module to use
            direction: "up" or "down"
            read_pause: If True, simulate reading behavior with longer variable pauses
        """
        direction_multiplier = -1 if direction == "up" else 1
        scroll_amount = amount * direction_multiplier

        chunk_size = self.config.scroll_chunk_size
        chunks = []
        remaining = abs(scroll_amount)

        while remaining > 0:
            # Varied chunk size (humans don't scroll by exact fixed units)
            actual_chunk = random.randint(max(1, chunk_size - 1), chunk_size + 1)
            chunk = min(actual_chunk, remaining)
            chunks.append(chunk)
            remaining -= chunk

        for i, chunk in enumerate(chunks):
            pyautogui_module.scroll(-chunk if direction == "down" else chunk)

            # Variable delay between chunks
            if read_pause and self.config.scroll_read_pause_min > 0:
                # Simulate reading: longer, more variable pauses
                delay = random.uniform(
                    self.config.scroll_read_pause_min,
                    self.config.scroll_read_pause_max
                )
            elif self.config.scroll_inertia_enabled and i == len(chunks) - 1:
                # Final chunk — deceleration/inertia
                delay = random.uniform(0.3, 0.8)
            else:
                delay = random.uniform(
                    self.config.scroll_chunk_delay_min,
                    self.config.scroll_chunk_delay_max
                )
            time.sleep(delay)

    def scroll_to_read(
        self,
        total_amount: int,
        pyautogui_module,
        direction: str = "down",
        num_reading_stops: int | None = None
    ):
        """
        Scroll while simulating natural reading behavior.

        Simulates a user reading content while scrolling — moves in bursts
        with variable pauses between reads. Common pattern for product pages
        on e-commerce sites.

        Args:
            total_amount: Total scroll units
            pyautogui_module: The pyautogui module to use
            direction: "up" or "down"
            num_reading_stops: Number of reading pauses (random 5–8 if None)
        """
        if num_reading_stops is None:
            num_reading_stops = random.randint(5, 8)

        per_stop = total_amount // num_reading_stops
        for _ in range(num_reading_stops):
            # Small scroll chunk (reading pace)
            small_chunk = max(1, per_stop // 3)
            for _ in range(random.randint(2, 4)):
                pyautogui_module.scroll(-small_chunk if direction == "down" else small_chunk)
                time.sleep(random.uniform(0.1, 0.25))
            # Reading pause
            time.sleep(random.uniform(
                self.config.scroll_read_pause_min,
                self.config.scroll_read_pause_max
            ))


# Preset configs export for external use
PRESET_CONFIGS = {
    "default": DEFAULT_CONFIG,
    "ecommerce_stealth": ECOMMERCE_STEALTH_CONFIG,
    "fast_relaxed": FAST_RELAXED_CONFIG,
}


def get_human_behavior_simulator(
    config: HumanBehaviorConfig | str | None = None
) -> Tuple[HumanMouseSimulator, HumanTypingSimulator, HumanScrollSimulator]:
    """
    Get or create human behavior simulator instances.

    Args:
        config: HumanBehaviorConfig instance, or preset name string
                ("default", "ecommerce_stealth", "fast_relaxed"), or None.

    Returns:
        Tuple of (mouse_simulator, typing_simulator, scroll_simulator)
    """
    global _human_mouse, _human_typing, _human_scroll, _human_config

    # Resolve preset string to config
    if isinstance(config, str):
        config = PRESET_CONFIGS.get(config, DEFAULT_CONFIG)

    if config is not None and config != _human_config:
        _human_config = config
        _human_mouse = None
        _human_typing = None
        _human_scroll = None

    if _human_mouse is None:
        _human_mouse = HumanMouseSimulator(_human_config)

    if _human_typing is None:
        _human_typing = HumanTypingSimulator(_human_config)

    if _human_scroll is None:
        _human_scroll = HumanScrollSimulator(_human_config)

    return _human_mouse, _human_typing, _human_scroll


def reset_simulators():
    """Reset all simulator instances (useful for new session)"""
    global _human_mouse, _human_typing, _human_scroll, _human_config
    _human_mouse = None
    _human_typing = None
    _human_scroll = None
    _human_config = None
