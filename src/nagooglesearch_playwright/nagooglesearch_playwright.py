#!/usr/bin/env python3

import asyncio, bot_safe_agents, dataclasses, datetime, enum, json, random, re, urllib.parse

from playwright.async_api import async_playwright, BrowserContext, Page, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from playwright._impl._errors import TargetClosedError as PlaywrightTargetClosedError

from bs4 import BeautifulSoup

def get_all_user_agents():
	"""
	Get a list of user agents.
	"""
	return bot_safe_agents.get_all()

def get_random_user_agent():
	"""
	Get a random user agent.
	"""
	return bot_safe_agents.get_random()

def get_tbs(date_from: datetime.datetime = None, date_to: datetime.datetime = None):
	"""
	Get a value for the 'to be searched' Google query parameter.
	"""
	date_format = "%m/%d/%Y"
	date_from = date_from.strftime(date_format) if date_from else ""
	date_to = date_to.strftime(date_format) if date_to else ""
	return f"cdr:1,cd_min:{date_from},cd_max:{date_to}"

class Error(enum.Enum):
	"""
	Enum containing various error states.
	"""
	PLAYWRIGHT = "PLAYWRIGHT_EXCEPTION"
	REQUEST = "REQUEST_EXCEPTION"
	RATE_LIMIT = "429_TOO_MANY_REQUESTS"

@dataclasses.dataclass
class GooglePagination:
	"""
	Class for storing Google pagination details.
	"""
	start: int = 0
	num: int = 10

@dataclasses.dataclass
class GoogleURLs:
	"""
	Class for storing Google URLs.
	"""
	homepage: str
	homepage_search: str
	search: str

class GoogleClient:

	def __init__(
		self,
		tld: str = "com",
		homepage_parameters: dict[str, str] = {
			"btnK": "Google+Search",
			"source": "hp"
		},
		search_parameters: dict[str, str] = {
		},
		cookies: dict[str, str] = {
		},
		user_agent: str = "",
		proxy: str = "",
		max_results: int = 100,
		min_sleep: int = 8,
		max_sleep: int = 18,
		consent_selector: str = "xpath=//img[@alt='Google']/../../following-sibling::div[2]/div/button[1]",
		headless: bool = True,
		humanize: bool = False,
		debug: bool = False
	):
		"""
		Class for Google searching.
		"""
		self.__tld: str = tld.lower()
		self.__homepage_parameters: dict[str, str] = homepage_parameters
		self.__search_parameters: dict[str, str] = search_parameters
		self.__pagination: GooglePagination = self.__get_pagination()
		self.__urls: GoogleURLs = self.__get_urls()
		self.__headers: dict[str, str] = self.__get_default_headers(user_agent)
		self.__cookies: list[dict[str, str]] = self.__get_default_cookies() if not cookies else self.__get_cookies(cookies)
		self.__proxy: str = self.__get_proxy(proxy)
		self.__max_results: int = max_results
		self.__min_sleep: int = min_sleep
		self.__max_sleep: int = max_sleep
		self.__consent_selector: str = consent_selector
		self.__headless: bool = headless
		self.__humanize: bool = humanize,
		self.__debug: bool = debug
		self.__error: Error = None

	def get_error(self) -> (Error | None):
		"""
		Get the current error, if any.
		"""
		return self.__error

	def __jdump(self, data: list[str] | dict[str, str]):
		"""
		Serialize a data to a JSON string.
		"""
		return json.dumps(data, indent = 4, ensure_ascii = False)

	def __print_debug(self, heading: str, text: int | str | list[str] | dict[str, str]):
		"""
		Print a debug information.
		"""
		if self.__debug:
			if isinstance(text, (list, dict)):
				text = self.__jdump(text)
			print(f"{heading}: {text}")

	def __get_pagination(self):
		"""
		Get Google pagination details.
		"""
		pagination = GooglePagination()
		if "start" in self.__search_parameters:
			pagination.start = int(self.__search_parameters["start"])
			self.__search_parameters.pop("start")
		if "num" in self.__search_parameters: # deprecated
			pagination.num = int(self.__search_parameters["num"])
			if pagination.num >= 10:
				pagination.num = 10
				self.__search_parameters.pop("num")
		return pagination

	def __get_urls(self):
		"""
		Get Google URLs.
		"""
		return GoogleURLs(
			homepage = self.__get_url(),
			homepage_search = self.__get_url("/search", self.__homepage_parameters | self.__search_parameters),
			search = self.__get_url("/search", self.__search_parameters)
		)

	def __get_url(self, path: str = "/", search_parameters: dict[str, str] = None) -> str:
		"""
		Get a Google URL.
		"""
		search_parameters = urllib.parse.urlencode(search_parameters, doseq = True) if search_parameters else ""
		return urllib.parse.urlunsplit(("https", f"www.google.{self.__tld}", path, search_parameters, ""))

	def __get_paginated_search_url(self):
		"""
		Get a paginated Google search URL.
		"""
		url = self.__urls.homepage_search
		if self.__pagination.start > 0:
			sep = "&" if self.__search_parameters else "?"
			url = f"{self.__urls.search}{sep}start={self.__pagination.start}"
		self.__pagination.start += self.__pagination.num
		return url

	def __get_default_headers(self, user_agent: str = ""):
		"""
		Get default HTTP request headers.
		"""
		if not user_agent:
			user_agent = get_random_user_agent()
		return {
			"User-Agent": user_agent,
			"Accept-Language": "en-US, *",
			"Accept": "*/*",
			"Referer": self.__urls.homepage,
			"Upgrade-Insecure-Requests": "1"
		}

	def __get_default_cookies(self):
		"""
		Get default HTTP cookies.\n
		This is a newer cookie consent mechanism.\n
		The below 'SOCS' and '__Secure-ENID' cookies reject all tracking and are valid for 13 months, created on 2026-03-20, but likely no longer work.
		More at: https://policies.google.com/technologies/cookies/embedded?hl=en-US
		Playwright handles this automatically - no default HTTP cookies are needed.
		"""
		return self.__get_cookies({
			# "SOCS": "CAESHAgBEhJnd3NfMjAyNjAzMTgtMF9SQzEaAmRlIAEaBgiAnPLNBg",
			# "__Secure-ENID": "32.SE=gBjbwa3RV0i1brALmGVI3rQ6ch-rqr6gH0NWaiITdV3_idyh6rX9yDJDePENSGmqM3VktRUwwGLuthhL6XsjoA4zX2kR0FsZyCBDjn689FPvuue7plDPey9pEUogNttvSUt7gVfYfl8XL6_0ntYRqGZkyzUSGQjR5h87zWXRy-3q4zmJeR0wcyNOfvJpniWoXZyB3a7JBFasgglVA3v6DclVvYmH7Esa8KnZbZ-mK3HxciG0pAqcucejfG1fyF19t9e95vGlaHT6-ZXwfEYhCxxgpptiTxQyuzUlAziTpsi3CXTdxOk"
		})

	def __get_cookies(self, cookies: dict[str, str]) -> list[dict[str, str]]:
		"""
		Get HTTP cookies.\n
		"""
		tmp = []
		if cookies:
			for name, value in cookies.items():
				tmp.append({
					"name": name,
					"value": value,
					"url": self.__urls.homepage
				})
		return tmp

	async def __update_consent_cookie(self, context: BrowserContext):
		"""
		Update the 'CONSENT' HTTP cookie.\n
		This is an older cookie consent mechanism.
		"""
		cookies = await context.cookies()
		key = "CONSENT"
		for cookie in cookies:
			if key == cookie["name"] and isinstance(cookie["value"], str) and re.search(r"PENDING\+[\d]+", cookie["value"], re.IGNORECASE):
				self.__print_debug("Info", f"Looks like your IP address is originating from an EU location. Your search results may vary. Attempting to work around this by updating the '{key}' cookie...")
				today = datetime.date.today().strftime("%Y%m%d")
				id = cookie["value"].split("+", 1)[-1]
				cookie["value"] = f"YES+shp.gws-{today}-0-RC1.en+FX+{id}"
				self.__print_debug(f"Updated '{key}' cookie", cookie["value"])
				await context.clear_cookies()
				await context.add_cookies(cookies)
				break

	def __get_proxy(self, proxy: str):
		"""
		Get an HTTP proxy.
		"""
		if proxy:
			proxy = urllib.parse.urlsplit(proxy).geturl()
		return proxy

	async def __sleep_random(self):
		"""
		Sleep for a random amount of time in seconds.
		"""
		sleep = random.randint(self.__min_sleep, self.__max_sleep)
		if sleep > 0:
			await asyncio.sleep(sleep)

	async def __get_page(self, page: Page, url: str):
		"""
		Send an HTTP GET request and return the HTML content of the response.
		"""
		self.__print_debug("Request URL", url)
		html = ""
		try:
			response = await page.goto(url, wait_until = "load")
			if not response:
				self.__error = Error.REQUEST
			else:
				self.__print_debug("Response Status Code", response.status)
				if response.status == 200:
					html = await page.content()
				elif response.status == 429:
					self.__error = Error.RATE_LIMIT
		except (PlaywrightError, PlaywrightTimeoutError, PlaywrightTargetClosedError) as ex:
			self.__error = Error.REQUEST
			self.__print_debug("Exception", str(ex))
		return html

	def __extract_links(self, html: str) -> list[str]:
		"""
		Extract links (URLs) from an HTML content.
		"""
		links = []
		soup = BeautifulSoup(html, "html.parser")
		search = soup.find(id = "search")
		if search:
			links = search.find_all("a", href = True)
		else:
			for id in ["gbar", "top_nav", "searchform"]:
				element = soup.find(id = id)
				if element:
					element.clear()
			links = soup.find_all("a", href = True)
		return [link["href"] for link in links]

	def __validate_link(self, link: str) -> str:
		"""
		Validate a link (URL).
		"""
		tmp = ""
		url = urllib.parse.urlsplit(link)
		scheme = url.scheme.lower()
		domain = url.netloc.lower()
		if domain and "google" not in domain:
			if scheme and "google" not in scheme and not domain.endswith("goo.gl"):
				tmp = url.geturl()
		else:
			query_string = urllib.parse.parse_qs(url.query)
			for key, value in query_string.items():
				if key in ["q", "u", "link"] and value:
					tmp = self.__validate_link(value[0])
					break
		return tmp.split("#:~:text=")[0]

	async def __get_browser_fingeprint(self, page: Page):
		if self.__debug:
			data = await page.evaluate("""
				() => ({
					platform: navigator.platform,
					hardware_concurrency: navigator.hardwareConcurrency,
					device_memory: navigator.deviceMemory,
					webdriver: navigator.webdriver,
					webgl_vendor: (() => {
						const webgl = document.createElement('canvas').getContext('webgl');
						if (webgl) {
							const ext = webgl.getExtension('WEBGL_debug_renderer_info');
							if (ext) {
								return webgl.getParameter(ext.UNMASKED_VENDOR_WEBGL);
							}
						}
						return null;
					})(),
					webgl_renderer: (() => {
						const webgl = document.createElement('canvas').getContext('webgl');
						if (webgl) {
							const ext = webgl.getExtension('WEBGL_debug_renderer_info');
							if (ext) {
								return webgl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
							}
						}
						return null;
					})()
				})
			""")
			self.__print_debug("Web Browser Details", data)

	async def __click_consent(self, page: Page):
		"""
		Click the consent button.
		"""
		if self.__consent_selector:
			await self.__sleep_random()
			consent = page.locator(self.__consent_selector)
			if await consent.count() > 0:
				await consent.first.click()

	async def __simulate_typed_search(self, page: Page):
		"""
		Simulate typed Google search.
		"""
		if self.__humanize:
			await self.__sleep_random()
			input_selector = "textarea[name='q']"
			await page.fill(input_selector, random.choice(["GitHub", "Python", "PyPi", "Playwright"]))
			await page.press(input_selector, "Enter")
			await page.wait_for_load_state("load")

	async def search(self) -> list[str]:
		"""
		Start a Google search.
		"""
		results = set()
		self.__error = None
		self.__print_debug("Initial Headers", self.__headers)
		self.__print_debug("Initial Cookies", {c["name"]: c["value"] for c in self.__cookies})
		self.__print_debug("Initial Proxy", self.__proxy)
		try:
			async with async_playwright() as playwright:
				async with await playwright.chromium.launch(
					headless = self.__headless,
					handle_sigint = False,
					args = ["--disable-blink-features=AutomationControlled"],
					ignore_default_args = ["--enable-automation"]
				) as browser:
					context = await browser.new_context(
						viewport = None,
						locale = "en-US",
						timezone_id = "Europe/Berlin",
						ignore_https_errors = True,
						java_script_enabled = True,
						accept_downloads = False,
						bypass_csp = False,
						extra_http_headers = self.__headers,
						proxy = {"server": self.__proxy} if self.__proxy else None
					)
					await context.add_cookies(self.__cookies)
					context.set_default_timeout(30000)
					page = await context.new_page()
					await self.__get_browser_fingeprint(page)
					await self.__get_page(page, self.__urls.homepage)
					if not self.__error:
						await self.__click_consent(page)
						await self.__update_consent_cookie(context)
						await self.__simulate_typed_search(page)
						self.__print_debug("Final Cookies", {c["name"]: c["value"] for c in await context.cookies()})
						while True:
							await self.__sleep_random()
							html = await self.__get_page(page, self.__get_paginated_search_url())
							# self.__print_debug("HTML", html)
							if self.__error or not html:
								break
							found = False
							for link in self.__extract_links(html):
								# self.__print_debug("Link", link)
								link = self.__validate_link(link)
								if link:
									found = True
									results.add(link)
							if not found or len(results) >= self.__max_results:
								break
						results = sorted(results, key = str.casefold)
		except asyncio.CancelledError:
			self.__error = Error.PLAYWRIGHT
			raise
		except (PlaywrightError, PlaywrightTimeoutError, PlaywrightTargetClosedError) as ex:
			self.__error = Error.PLAYWRIGHT
			self.__print_debug("Exception", str(ex))
		results = list(results)
		# self.__print_debug("Results", results)
		return results
