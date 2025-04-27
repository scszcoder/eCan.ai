::cd C:\Users\songc\PycharmProjects\ecbot\ecbot-ui
::call yarn
::call yarn build
cd C:\Users\songc\PycharmProjects\ecbot
C:\Users\songc\PycharmProjects\ecbot\venv\Scripts\pyinstaller.exe --noconfirm --onedir --windowed ^
--icon "C:/Users/songc/ECBot.ico" ^
--name "ECBot" ^
--additional-hooks-dir "./hook" ^
--clean ^
--add-data "./esprima.jsss;esprima.jsss" ^
--add-data "./bot;bot/" ^
--add-data "./gui;gui/" ^
--add-data "./common;common/" ^
--add-data "./config;config/" ^
--add-data "./hooks;hooks/" ^
--add-data "./chromedriver-win64;chromedriver-win64/" ^
--add-data "./ecbot-ui;ecbot-ui/" ^
--add-data "./my_rais_extensions;my_rais_extensions/" ^
--add-data "./globals;globals/" ^
--add-data "./resource;resource/" ^
--add-data "./tests;tests/" ^
--add-data "./utils;utils/" ^
--add-data "./venv;venv/" ^
--add-data "./venv/Lib/site-packages/acres;acres/" ^
--add-data "./venv/Lib/site-packages/aioconsole;aioconsole/" ^
--add-data "./venv/Lib/site-packages/aiofiles;aiofiles/" ^

--add-data "./venv/Lib/site-packages/aiohappyeyeballs;aiohappyeyeballs/" ^
--add-data "./venv//Lib/site-packages/aiohttp;aiohttp/" ^
--add-data "./venv/Lib/site-packages/aiolimiter;aiolimiter/" ^
--add-data "./venv/Lib/site-packages/aiosignal;aiosignal/" ^
--add-data "./venv//Lib/site-packages/altgraph;altgraph/" ^
--add-data "./venv//Lib/site-packages/annotated-types;annotated-types/" ^
--add-data "./venv//Lib/site-packages/anyio;anyio/" ^
--add-data "./venv//Lib/site-packages/anytree;anytree/" ^

--add-data "./venv//Lib/site-packages/apiclient;apiclient/" ^
--add-data "./venv//Lib/site-packages/asgiref;asgiref/" ^
--add-data "./venv//Lib/site-packages/asttokens;asttokens/" ^
--add-data "./venv//Lib/site-packages/async_timeout;async_timeout/" ^
--add-data "./venv//Lib/site-packages/asyncclick;asyncclick/" ^

--add-data "./venv//Lib/site-packages/attrs;attrs/" ^
--add-data "./venv//Lib/site-packages/autograd;autograd/" ^
--add-data "./venv//Lib/site-packages/axios;axios/" ^

--add-data "./venv/Lib/site-packages/backcall;backcall/" ^
--add-data "./venv/Lib/site-packages/backoff;backoff/" ^
--add-data "./venv/Lib/site-packages/bcrypt;bcrypt/" ^
--add-data "./venv/Lib/site-packages/bleach;bleach/" ^
--add-data "./venv/Lib/site-packages/blinker;blinker/" ^
--add-data "./venv/Lib/site-packages/botocore;botocore/" ^
--add-data "./venv/Lib/site-packages/boto3;boto3/" ^
--add-data "./venv/Lib/site-packages/bs4;bs4/" ^
--add-data "./venv/Lib/site-packages/build;build/" ^

--add-data "./venv//Lib/site-packages/cachetools;cachetools/" ^
--add-data "./venv//Lib/site-packages/certifi;certifi/" ^
--add-data "./venv//Lib/site-packages/cffi;cffi/" ^
--add-data "./venv//Lib/site-packages/chardet;chardet/" ^
--add-data "./venv//Lib/site-packages/charset-normalizer;charset-normalizer/" ^
--add-data "./venv//Lib/site-packages/chroma-hnswlib;chroma-hnswlib/" ^
--add-data "./venv//Lib/site-packages/chromadb;chromadb/" ^
--add-data "./venv//Lib/site-packages/ci-info;ci-info/" ^
--add-data "./venv//Lib/site-packages/click;click/" ^
--add-data "./venv//Lib/site-packages/colorama;colorama/" ^
--add-data "./venv//Lib/site-packages/coloredlogs;coloredlogs/" ^
--add-data "./venv//Lib/site-packages/colorlog;colorlog/" ^
--add-data "./venv//Lib/site-packages/configobj;configobj/" ^
--add-data "./venv//Lib/site-packages/configparser;configparser/" ^
--add-data "./venv//Lib/site-packages/crontab;crontab/" ^
--add-data "./venv/Lib/site-packages/cryptography;cryptography/" ^
--add-data "./venv/Lib/site-packages/cv2;cv2/" ^

--add-data "./venv/Lib/site-packages/dateutil;dateutil/" ^
--add-data "./venv/Lib/site-packages/decorator;decorator/" ^
--add-data "./venv/Lib/site-packages/deepdiff;deepdiff/" ^
--add-data "./venv/Lib/site-packages/defusedxml;defusedxml/" ^
--add-data "./venv/Lib/site-packages/distro;distro/" ^
--add-data "./venv/Lib/site-packages/docopt;docopt/" ^
--add-data "./venv/Lib/site-packages/durationpy;durationpy/" ^

--add-data "./venv/Lib/site-packages/EasyProcess;EasyProcess/" ^
--add-data "./venv/Lib/site-packages/entrypoint2;entrypoint2/" ^
--add-data "./venv/Lib/site-packages/envs;envs/" ^
--add-data "./venv/Lib/site-packages/esprima;esprima/" ^
--add-data "./venv/Lib/site-packages/et_xmlfile;et_xmlfile/" ^
--add-data "./venv/Lib/site-packages/etelemetry;etelemetry/" ^
--add-data "./venv/Lib/site-packages/executing;executing/" ^

--add-data "./venv/Lib/site-packages/faiss-cpu;faiss-cpu/" ^
--add-data "./venv/Lib/site-packages/fastapi;fastapi/" ^
--add-data "./venv/Lib/site-packages/fastjsonschema;fastjsonschema/" ^
--add-data "./venv/Lib/site-packages/filelock;filelock/" ^
--add-data "./venv/Lib/site-packages/fitz;fitz/" ^
--add-data "./venv/Lib/site-packages/Flask;Flask/" ^
--add-data "./venv/Lib/site-packages/Flask-Cors;Flask-Cors/" ^
--add-data "./venv/Lib/site-packages/flatbuffers;flatbuffers/" ^
--add-data "./venv/Lib/site-packages/frozenlist;frozenlist/" ^
--add-data "./venv/Lib/site-packages/fsspec;fsspec/" ^
--add-data "./venv/Lib/site-packages/future;future/" ^
--add-data "./venv/Lib/site-packages/fuzzywuzzy;fuzzywuzzy/" ^

--add-data "./venv/Lib/site-packages/gevent;gevent/" ^
--add-data "./venv/Lib/site-packages/google-api-cor;google-api-cor/" ^
--add-data "./venv/Lib/site-packages/google-api-python-client;google-api-python-client/" ^
--add-data "./venv/Lib/site-packages/google-auth;google-auth/" ^
--add-data "./venv/Lib/site-packages/google-auth-httplib2;google-auth-httplib2/" ^
--add-data "./venv/Lib/site-packages/google-auth-oauthlib;google-auth-oauthlib/" ^
--add-data "./venv/Lib/site-packages/googleapis-common-protos;googleapis-common-protos/" ^
--add-data "./venv/Lib/site-packages/greenlet;greenlet/" ^
--add-data "./venv/Lib/site-packages/grpcio;grpcio/" ^

--add-data "./venv/Lib/site-packages/h11;h11/" ^
--add-data "./venv/Lib/site-packages/httpcore;httpcore/" ^
--add-data "./venv/Lib/site-packages/httplib2;httplib2/" ^
--add-data "./venv/Lib/site-packages/httptools;httptools/" ^
--add-data "./venv/Lib/site-packages/httpx;httpx/" ^
--add-data "./venv/Lib/site-packages/httpx-sse;httpx-sse/" ^
--add-data "./venv/Lib/site-packages/huggingface-hub;huggingface-hub/" ^
--add-data "./venv/Lib/site-packages/humanfriendly;humanfriendly/" ^

--add-data "./venv/Lib/site-packages/idna;idna/" ^
--add-data "./venv/Lib/site-packages/importlib_metadata;importlib_metadata/" ^
--add-data "./venv/Lib/site-packages/importlib_resources;importlib_resources/" ^
--add-data "./venv/Lib/site-packages/ipython;ipython/" ^
--add-data "./venv/Lib/site-packages/isodate;isodate/" ^
--add-data "./venv/Lib/site-packages/itsdangerous;itsdangerous/" ^

--add-data "./venv/Lib/site-packages/jedi;jedi/" ^
--add-data "./venv/Lib/site-packages/Jinja2;Jinja2/" ^
--add-data "./venv/Lib/site-packages/jiter;jiter/" ^
--add-data "./venv/Lib/site-packages/jmespath;jmespath/" ^
--add-data "./venv/Lib/site-packages/joblib;joblib/" ^
--add-data "./venv/Lib/site-packages/jsonpatch;jsonpatch/" ^
--add-data "./venv/Lib/site-packages/jsonpointer;jsonpointer/" ^
--add-data "./venv/Lib/site-packages/jsonschema;jsonschema/" ^
--add-data "./venv/Lib/site-packages/jsonschema-specifications;jsonschema-specifications/" ^
--add-data "./venv/Lib/site-packages/jupyter_client;jupyter_client/" ^
--add-data "./venv/Lib/site-packages/jupyter_core;jupyter_core/" ^
--add-data "./venv/Lib/site-packages/jupyterlab_pygments;jupyterlab_pygments/" ^

--add-data "./venv//Lib/site-packages/keyboard;keyboard/" ^
--add-data "./venv//Lib/site-packages/kubernetes;kubernetes/" ^

--add-data "./venv/Lib/site-packages/langchain;langchain/" ^
--add-data "./venv/Lib/site-packages/langchain-core;langchain-core/" ^
--add-data "./venv/Lib/site-packages/langchain_mcp_adapters;langchain_mcp_adapters/" ^
--add-data "./venv/Lib/site-packages/langchain_openai;langchain_openai/" ^
--add-data "./venv/Lib/site-packages/langchain-text-splitters;langchain-text-splitters/" ^
--add-data "./venv/Lib/site-packages/langcodes;langcodes/" ^
--add-data "./venv/Lib/site-packages/langgraph_sdk;langgraph_sdk/" ^
--add-data "./venv/Lib/site-packages/langgraph;langgraph/" ^
--add-data "./venv/Lib/site-packages/langsmith;langsmith/" ^

--add-data "./venv/Lib/site-packages/Levenshtein;Levenshtein/" ^
--add-data "./venv/Lib/site-packages/looseversion;looseversion/" ^
--add-data "./venv/Lib/site-packages/lxml;lxml/" ^

--add-data "./venv//Lib/site-packages/markdown-it-py;markdown-it-py/" ^
--add-data "./venv//Lib/site-packages/MarkupSafe;MarkupSafe/" ^
--add-data "./venv//Lib/site-packages/matplotlib-inline;matplotlib-inline/" ^
--add-data "./venv//Lib/site-packages/mcp;mcp/" ^
--add-data "./venv//Lib/site-packages/mdurl;mdurl/" ^
--add-data "./venv//Lib/site-packages/mistune;mistune/" ^
--add-data "./venv//Lib/site-packages/mmh3;mmh3/" ^
--add-data "./venv//Lib/site-packages/monotonic;monotonic/" ^
--add-data "./venv//Lib/site-packages/mouseinfo;mouseinfo/" ^
--add-data "./venv//Lib/site-packages/mpmath;mpmath/" ^
--add-data "./venv//Lib/site-packages/mss;mss/" ^
--add-data "./venv//Lib/site-packages/multidict;multidict/" ^

--add-data "./venv/Lib/site-packages/nbclient;nbclient/" ^
--add-data "./venv/Lib/site-packages/nbconvert;nbconvert/" ^
--add-data "./venv/Lib/site-packages/nbformat;nbformat/" ^
--add-data "./venv/Lib/site-packages/networkx;networkx/" ^
--add-data "./venv/Lib/site-packages/nibabel;nibabel/" ^
--add-data "./venv/Lib/site-packages/nipype;nipype/" ^
--add-data "./venv/Lib/site-packages/numpy;numpy/" ^

--add-data "./venv/Lib/site-packages/oauthlib;oauthlib/" ^
--add-data "./venv/Lib/site-packages/onnxruntime;onnxruntime/" ^
--add-data "./venv/Lib/site-packages/openai;openai/" ^
--add-data "./venv/Lib/site-packages/openpyxl;openpyxl/" ^
--add-data "./venv/Lib/site-packages/opentelemetry;opentelemetry/" ^
--add-data "./venv/Lib/site-packages/orderly-set;orderly-set/" ^
--add-data "./venv/Lib/site-packages/ordlookup;ordlookup/" ^
--add-data "./venv/Lib/site-packages/orjson;orjson/" ^
--add-data "./venv/Lib/site-packages/outcome;outcome/" ^
--add-data "./venv/Lib/site-packages/overrides;overrides/" ^

--add-data "./venv//Lib/site-packages/pandas;pandas/" ^
--add-data "./venv//Lib/site-packages/pandocfilters;pandocfilters/" ^
--add-data "./venv//Lib/site-packages/parso;parso/" ^
--add-data "./venv//Lib/site-packages/pathlib;pathlib/" ^
--add-data "./venv/Lib/site-packages/pdf2image;pdf2image/" ^
--add-data "./venv/Lib/site-packages/pefile;pefile/" ^
--add-data "./venv/Lib/site-packages/pickleshare;pickleshare/" ^
--add-data "./venv//Lib/site-packages/ping3;ping3/" ^
--add-data "./venv/Lib/site-packages/platformdirs;platformdirs/" ^
--add-data "./venv/Lib/site-packages/posthog;posthog/" ^
--add-data "./venv/Lib/site-packages/prompt_toolkit;prompt_toolkit/" ^
--add-data "./venv/Lib/site-packages/propcache;propcache/" ^
--add-data "./venv/Lib/site-packages/proto-plus;proto-plus/" ^
--add-data "./venv/Lib/site-packages/protobuf;protobuf/" ^
--add-data "./venv/Lib/site-packages/prov;prov/" ^
--add-data "./venv/Lib/site-packages/psutil;psutil/" ^
--add-data "./venv/Lib/site-packages/pure_eval;pure_eval/" ^
--add-data "./venv/Lib/site-packages/puremagic;puremagic/" ^
--add-data "./venv/Lib/site-packages/py-cpuinfo;py-cpuinfo/" ^
--add-data "./venv/Lib/site-packages/pyasn1;pyasn1/" ^
--add-data "./venv/Lib/site-packages/pyasn1_modules;pyasn1_modules/" ^
--add-data "./venv/Lib/site-packages/pyautogui;pyautogui/" ^
--add-data "./venv/Lib/site-packages/pycognito;pycognito/" ^
--add-data "./venv/Lib/site-packages/pycparser;pycparser/" ^
--add-data "./venv/Lib/site-packages/pydantic;pydantic/" ^
--add-data "./venv/Lib/site-packages/pydantic_settings;pydantic_settings/" ^
--add-data "./venv/Lib/site-packages/pydantic_core;pydantic_core/" ^
--add-data "./venv/Lib/site-packages/pydot;pydot/" ^
--add-data "./venv/Lib/site-packages/pygetwindow;pygetwindow/" ^
--add-data "./venv/Lib/site-packages/pygments;pygments/" ^
--add-data "./venv//Lib/site-packages/pymsgbox;pymsgbox/" ^
--add-data "./venv//Lib/site-packages/pymupdf;pymupdf/" ^
--add-data "./venv/Lib/site-packages/pynput;pynput/" ^

--add-data "./venv/Lib/site-packages/pyperclip;pyperclip/" ^
--add-data "./venv/Lib/site-packages/pyqtgraph;pyqtgraph/" ^
--add-data "./venv/Lib/site-packages/pyrect;pyrect/" ^
--add-data "./venv//Lib/site-packages/pyscreenshot;pyscreenshot/" ^
--add-data "./venv//Lib/site-packages/pyscreeze;pyscreeze/" ^
--add-data "./venv//Lib/site-packages/pytesseract;pytesseract/" ^

--add-data "./venv/Lib/site-packages/pythonwin;pythonwin/" ^
--add-data "./venv/Lib/site-packages/pytweening;pytweening/" ^
--add-data "./venv/Lib/site-packages/pytz;pytz/" ^
--add-data "./venv/Lib/site-packages/pywin32_system32;pywin32_system32/" ^
--add-data "./venv/Lib/site-packages/pyxnat;pyxnat/" ^
--add-data "./venv/Lib/site-packages/PIL;PIL/" ^
--add-data "./venv/Lib/site-packages/PyPDF2;PyPDF2/" ^
--add-data "./venv/Lib/site-packages/PySide6;PySide6/" ^

--add-data "./venv/Lib/site-packages/qasync;qasync/" ^
--add-data "./venv/Lib/site-packages/qtpy;qtpy/" ^

--add-data "./venv/Lib/site-packages/rapidfuzz;rapidfuzz/" ^
--add-data "./venv/Lib/site-packages/rdflib;rdflib/" ^
--add-data "./venv/Lib/site-packages/regex;regex/" ^
--add-data "./venv/Lib/site-packages/requests;requests/" ^
--add-data "./venv/Lib/site-packages/requests_aws4auth;requests_aws4auth/" ^
--add-data "./venv/Lib/site-packages/requests_oauthlib;requests_oauthlib/" ^
--add-data "./venv/Lib/site-packages/requests_toolbelt;requests_toolbelt/" ^
--add-data "./venv/Lib/site-packages/rich;rich/" ^
--add-data "./venv/Lib/site-packages/rpds;rpds/" ^
--add-data "./venv/Lib/site-packages/rsa;rsa/" ^

--add-data "./venv/Lib/site-packages/s3transfer;s3transfer/" ^
--add-data "./venv/Lib/site-packages/safetensors;safetensors/" ^
--add-data "./venv/Lib/site-packages/schedule;schedule/" ^
--add-data "./venv/Lib/site-packages/scipy;scipy/" ^
--add-data "./venv/Lib/site-packages/scripts;scripts/" ^
--add-data "./venv/Lib/site-packages/selenium;selenium/" ^
--add-data "./venv//Lib/site-packages/setproctitle;setproctitle/" ^
--add-data "./venv//Lib/site-packages/sentence_transformers;sentence_transformers/" ^
--add-data "./venv//Lib/site-packages/setuptools;setuptools/" ^
--add-data "./venv//Lib/site-packages/shellingham;shellingham/" ^
--add-data "./venv//Lib/site-packages/shiboken6;shiboken6/" ^
--add-data "./venv/Lib/site-packages/simplejson;simplejson/" ^
--add-data "./venv/Lib/site-packages/sklearn;sklearn/" ^
--add-data "./venv/Lib/site-packages/six.py;." ^
--add-data "./venv/Lib/site-packages/sortedcontainers;sortedcontainers/" ^
--add-data "./venv/Lib/site-packages/sniffio;sniffio/" ^
--add-data "./venv/Lib/site-packages/soupsieve;soupsieve/" ^
--add-data "./venv//Lib/site-packages/sqlalchemy;sqlalchemy/" ^
--add-data "./venv//Lib/site-packages/sse_starlette;sse_starlette/" ^
--add-data "./venv//Lib/site-packages/stack_data;stack_data/" ^
--add-data "./venv//Lib/site-packages/starlette;starlette/" ^
--add-data "./venv//Lib/site-packages/sympy;sympy/" ^

--add-data "./venv/Lib/site-packages/tests;tests/" ^
--add-data "./venv/Lib/site-packages/tenacity;tenacity/" ^
--add-data "./venv/Lib/site-packages/tinycss2;tinycss2/" ^
--add-data "./venv/Lib/site-packages/tokenizers;tokenizers/" ^
--add-data "./venv/Lib/site-packages/torch;torch/" ^
--add-data "./venv/Lib/site-packages/torchgen;torchgen/" ^
--add-data "./venv/Lib/site-packages/tornado;tornado/" ^
--add-data "./venv/Lib/site-packages/tqdm;tqdm/" ^
--add-data "./venv/Lib/site-packages/traitlets;traitlets/" ^
--add-data "./venv/Lib/site-packages/traits;traits/" ^
--add-data "./venv/Lib/site-packages/transformers;transformers/" ^
--add-data "./venv/Lib/site-packages/transitions;transitions/" ^
--add-data "./venv/Lib/site-packages/trio;trio/" ^
--add-data "./venv/Lib/site-packages/trio_websocket;trio_websocket/" ^
--add-data "./venv/Lib/site-packages/twocaptcha;twocaptcha/" ^
--add-data "./venv/Lib/site-packages/typer;typer/" ^
--add-data "./venv/Lib/site-packages/typing_inspection;typing_inspection/" ^

--add-data "./venv/Lib/site-packages/tzdata;tzdata/" ^
--add-data "./venv/Lib/site-packages/tzlocal;tzlocal/" ^

--add-data "./venv/Lib/site-packages/umap;umap/" ^

--add-data "./venv/Lib/site-packages/uritemplate;uritemplate/" ^
--add-data "./venv/Lib/site-packages/urllib3;urllib3/" ^
--add-data "./venv/Lib/site-packages/uvicorn;uvicorn/" ^

--add-data "./venv/Lib/site-packages/validate;validate/" ^
--add-data "./venv/Lib/site-packages/wasabi;wasabi/" ^

--add-data "./venv/Lib/site-packages/watchdog;watchdog/" ^
--add-data "./venv/Lib/site-packages/watchfiles;watchfiles/" ^
--add-data "./venv/Lib/site-packages/wcwidth;wcwidth/" ^
--add-data "./venv//Lib/site-packages/weasel;weasel/" ^

--add-data "./venv/Lib/site-packages/webdriver_manager;webdriver_manager/" ^
--add-data "./venv//Lib/site-packages/webencodings;webencodings/" ^
--add-data "./venv//Lib/site-packages/websockets;websockets/" ^

--add-data "./venv/Lib/site-packages/werkzeug;werkzeug/" ^
--add-data "./venv/Lib/site-packages/win32;win32/" ^
--add-data "./venv/Lib/site-packages/win32com;win32com/" ^
--add-data "./venv/Lib/site-packages/win32comext;win32comext/" ^
--add-data "./venv/Lib/site-packages/win32ctypes;win32ctypes/" ^
--add-data "./venv/Lib/site-packages/wrapt;wrapt/" ^
--add-data "./venv/Lib/site-packages/wsproto;wsproto/" ^

--add-data "./venv/Lib/site-packages/xlrd;xlrd/" ^

--add-data "./venv/Lib/site-packages/yaml;yaml/" ^
--add-data "./venv/Lib/site-packages/yarg;yarg/" ^
--add-data "./venv/Lib/site-packages/yarl;yarl/" ^

--add-data "./venv/Lib/site-packages/zipp;zipp/" ^
--add-data "./venv/Lib/site-packages/zmq;zmq/" ^
--add-data "./venv/Lib/site-packages/zope;zope/" ^
--add-data "./venv/Lib/site-packages/zstandard;zstandard/" ^

--hiddenimport "__future__" ^
--hiddenimport "xml.etree.ElementTree" ^
--hiddenimport "html" ^
--hiddenimport "html.parser" ^
--hiddenimport "uuid" ^
--hiddenimport "typing_extensions" ^
--hiddenimport "python_Levenshtein" ^
--hiddenimport "configparser" ^
--hiddenimport "http.cookies" ^
--hiddenimport "importlib.resources" ^
--hiddenimport "cProfile" ^
--paths "." ^
--paths "./agent" ^
--paths "./bot" ^
--paths "./browser" ^
--paths "./chromedriver-win64" ^
--paths "./common" ^
--paths "./config" ^
--paths "./dom" ^
--paths "./ecbot-ui" ^
--paths "./globals" ^
--paths "./gui" ^
--paths "./hooks" ^
--paths "./my_rais_extensions" ^
--paths "./tests" ^
--paths "./utils" ^
--paths "C:/Python310/Lib" ^
--workpath "C:/Users/songc/ECBot_build" ^
--distpath "C:/Users/songc/ECBotApp" ^
"./main.py"
cd C:\Users\songc\ECBotApp
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" .\packECBot.iss


