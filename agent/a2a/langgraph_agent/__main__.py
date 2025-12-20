from agent.a2a.common.server import A2AServer
from agent.a2a.common.types import AgentCard, AgentCapabilities, AgentSkill, MissingAPIKeyError
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
from agent.a2a.langgraph_agent.task_manager import AgentTaskManager
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
import click
import os
import logging
from dotenv import load_dotenv
import sys

# Ensure Windows uses SelectorEventLoop to support subprocesses (e.g., Playwright)
try:
    if sys.platform.startswith("win"):
        import asyncio as _asyncio
        _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
except Exception:
    pass

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@click.command()
@click.option("--host", "host", default="localhost")
@click.option("--port", "port", default=10000)
def main(host, port):
    """Starts the Currency Agent server.
    
    Note: This standalone server requires an LLM instance from MainWindow.
    For production use, use the agent through MainWindow instead.
    """
    try:
        if not os.getenv("GOOGLE_API_KEY"):
            raise MissingAPIKeyError("GOOGLE_API_KEY environment variable not set.")

        # This standalone server cannot work without mainwin.llm
        # In production, agents should be created through MainWindow which provides mainwin.llm
        raise ValueError(
            "This standalone server requires mainwin.llm from MainWindow. "
            "Please use the agent through MainWindow instead, or modify this script to accept an LLM instance."
        )

        capabilities = AgentCapabilities(streaming=True, pushNotifications=True)
        skill = AgentSkill(
            id="convert_currency",
            name="Currency Exchange Rates Tool",
            description="Helps with exchange values between various currencies",
            tags=["currency conversion", "currency exchange"],
            examples=["What is exchange rate between USD and GBP?"],
        )
        agent_card = AgentCard(
            name="Currency Agent",
            description="Helps with exchange rates for currencies",
            url=f"http://{host}:{port}",
            version="1.0.0",
            defaultInputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            defaultOutputModes=ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            capabilities=capabilities,
            skills=[skill],
        )

        notification_sender_auth = PushNotificationSenderAuth()
        notification_sender_auth.generate_jwk()
        # ECRPAHelperAgent now requires llm parameter from mainwin
        # This standalone server cannot provide it, so it will fail
        server = A2AServer(
            agent_card=agent_card,
            task_manager=AgentTaskManager(agent=ECRPAHelperAgent(llm=None), notification_sender_auth=notification_sender_auth),
            host=host,
            port=port,
        )

        server.app.add_route(
            "/.well-known/jwks.json", notification_sender_auth.handle_jwks_endpoint, methods=["GET"]
        )

        logger.info(f"Starting server on {host}:{port}")
        server.start()
    except MissingAPIKeyError as e:
        logger.error(f"Error: {e}")
        exit(1)
    except Exception as e:
        logger.error(f"An error occurred during server startup: {e}")
        exit(1)


if __name__ == "__main__":
    main()
