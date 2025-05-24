from typing import Any, Dict, List, Literal, Optional, Type
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model
import uuid

class GlobalContext(BaseModel):
    context_id: str = str(uuid.uuid4())
    contexts: dict = {}         # {"app_name": "app_context", ....} "ecbot" being the internal rpa runs.
    global_state: str = "closed"

    async def get_states(self):
        states_only = {key: value["state"] for key, value in self.contexts.items()}
        return states_only

    async def get_global_state(self):
        return self.global_state


class AppContext(BaseModel):
    context_id: str = str(uuid.uuid4())
    name: str = "browser"
    config: dict = Any
    category: str = 'browser'
    state: str = "closed"

    async def set_state(self, state):
        self.state = state

    async def get_state(self):
        return self.state

class Personality(BaseModel):
    id: str = str(uuid.uuid4())
    first_name: str = "John"
    last_name: str = "Smith"
    gender: str = "Male"
    Character: str = ''
    Age: int = 25