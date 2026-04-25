from browser_use import Agent
from agent.ec_skills.browser_use_extension.cloud_llm import CloudLLM
from agent.ec_skills.browser_use_extension.cloud_agent import CloudAgent
from browser_use.browser import Browser
import asyncio

async def main():

    cloud_llm = CloudLLM(
        cloud_endpoint="https://your-cloud.com/api/browser-use",
        api_key="your-api-key"
    )

    browser = Browser(llm=cloud_llm)

    agent = CloudAgent(
        task="Find the top post on Hacker News",
        cloud_endpoint="https://your-cloud.com/api/browser-agent",
        cloud_api_key="your-api-key",
        browser=browser
    )

    await agent.run()
