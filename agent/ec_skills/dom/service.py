import gc
import json
import logging
from dataclasses import dataclass
from importlib import resources
from typing import TYPE_CHECKING, Optional, Tuple
from urllib.parse import urlparse


if TYPE_CHECKING:
	from selenium.webdriver.remote.webdriver import WebDriver
	from selenium.common.exceptions import JavascriptException

from agent.ec_skills.dom.views import (
	DOMBaseNode,
	DOMElementNode,
	DOMState,
	DOMTextNode,
	SelectorMap,
)
from agent.run_utils import time_execution_async

logger = logging.getLogger(__name__)


@dataclass
class ViewportInfo:
	width: int
	height: int


class DomService:
	def __init__(self, driver: 'WebDriver'):
		self.driver = driver
		self.xpath_cache = {}
		self.js_code = resources.files('browser_use.dom').joinpath('buildDomTree.js').read_text()

	# region - Clickable elements
	@time_execution_async('--get_clickable_elements')
	async def get_clickable_elements(
			self,
			highlight_elements: bool = True,
			focus_element: int = -1,
			viewport_expansion: int = 0,
	) -> DOMState:
		element_tree, selector_map = self._build_dom_tree(highlight_elements, focus_element, viewport_expansion)
		return DOMState(element_tree=element_tree, selector_map=selector_map)

	@time_execution_async('--get_cross_origin_iframes')
	async def get_cross_origin_iframes(self) -> list[str]:
		iframe_elements = self.driver.find_elements("tag name", "iframe")
		hidden_frame_urls = [
            iframe.get_attribute("src") for iframe in iframe_elements
            if not iframe.is_displayed()
        ]

		current_url = self.driver.current_url
		current_domain = urlparse(current_url).netloc

		def is_ad_url(url):
			return any(domain in urlparse(url).netloc for domain in (
                'doubleclick.net', 'adroll.com', 'googletagmanager.com'
            ))

		frames = self.driver.find_elements("tag name", "iframe")
		frame_urls = []
		for frame in frames:
			src = frame.get_attribute("src")
			if not src:
				continue

			parsed = urlparse(src)
			if not parsed.netloc:
				continue

			if parsed.netloc != current_domain and src not in hidden_frame_urls and not is_ad_url(src):
				frame_urls.append(src)

		return frame_urls

	async def _construct_dom_tree(self, eval_page: dict) -> Tuple[DOMElementNode, SelectorMap]:
		js_node_map = eval_page['map']
		js_root_id = eval_page['rootId']

		selector_map = {}
		node_map = {}

		for id, node_data in js_node_map.items():
			node, children_ids = self._parse_node(node_data)
			if node is None:
				continue

			node_map[id] = node

			if isinstance(node, DOMElementNode) and node.highlight_index is not None:
				selector_map[node.highlight_index] = node

			if isinstance(node, DOMElementNode):
				for child_id in children_ids:
					if child_id not in node_map:
						continue

					child_node = node_map[child_id]
					child_node.parent = node
					node.children.append(child_node)

		html_to_dict = node_map[str(js_root_id)]

		del node_map
		del js_node_map
		del js_root_id

		gc.collect()

		if html_to_dict is None or not isinstance(html_to_dict, DOMElementNode):
			raise ValueError('Failed to parse HTML to dictionary')

		return html_to_dict, selector_map


	@time_execution_async('--build_dom_tree')
	async def _build_dom_tree(
        self,
        highlight_elements: bool,
        focus_element: int,
        viewport_expansion: int,
    ) -> Tuple[DOMElementNode, SelectorMap]:

		if self.driver.execute_script('return 1 + 1') != 2:
			raise ValueError('The page cannot evaluate javascript code properly')

		if self.driver.current_url == 'about:blank':
			return (
                DOMElementNode(
                    tag_name='body',
                    xpath='',
                    attributes={},
                    children=[],
                    is_visible=False,
                    parent=None,
                ),
                {},
            )

		debug_mode = logger.getEffectiveLevel() == logging.DEBUG
		args = {
            'doHighlightElements': highlight_elements,
            'focusHighlightIndex': focus_element,
            'viewportExpansion': viewport_expansion,
            'debugMode': debug_mode,
        }

		try:
			eval_page = self.driver.execute_script(f"return ({self.js_code})({json.dumps(args)})")
		except JavascriptException as e:
			logger.error('Error evaluating JavaScript: %s', e)
			raise

		if debug_mode and 'perfMetrics' in eval_page:
			logger.debug(
                'DOM Tree Building Performance Metrics for: %s\n%s',
                self.driver.current_url,
                json.dumps(eval_page['perfMetrics'], indent=2),
            )

		return await self._construct_dom_tree(eval_page)

	def _parse_node(self, node_data: dict) -> Tuple[Optional[DOMBaseNode], list[int]]:
		if not node_data:
			return None, []

		if node_data.get('type') == 'TEXT_NODE':
			text_node = DOMTextNode(
				text=node_data['text'],
				is_visible=node_data['isVisible'],
				parent=None,
			)
			return text_node, []

		viewport_info = None
		if 'viewport' in node_data:
			viewport_info = ViewportInfo(
				width=node_data['viewport']['width'],
				height=node_data['viewport']['height'],
			)

		element_node = DOMElementNode(
			tag_name=node_data['tagName'],
			xpath=node_data['xpath'],
			attributes=node_data.get('attributes', {}),
			children=[],
			is_visible=node_data.get('isVisible', False),
			is_interactive=node_data.get('isInteractive', False),
			is_top_element=node_data.get('isTopElement', False),
			is_in_viewport=node_data.get('isInViewport', False),
			highlight_index=node_data.get('highlightIndex'),
			shadow_root=node_data.get('shadowRoot', False),
			parent=None,
			viewport_info=viewport_info,
		)

		children_ids = node_data.get('children', [])
		return element_node, children_ids