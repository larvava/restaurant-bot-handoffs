import dotenv

dotenv.load_dotenv()

import asyncio
import streamlit as st
from agents import (
    Agent,
    Runner,
    RunContextWrapper,
    SQLiteSession,
    handoff,
)
from agents.extensions import handoff_filters
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from models import HandoffData
from my_agents.menu_agent import menu_agent
from my_agents.order_agent import order_agent
from my_agents.reservation_agent import reservation_agent


def handle_handoff(
    wrapper: RunContextWrapper,
    input_data: HandoffData,
):
    with st.sidebar:
        st.write(
            f"""
            Handing off to {input_data.to_agent_name}
            Reason: {input_data.reason}
            Issue Type: {input_data.issue_type}
            Description: {input_data.issue_description}
            """
        )


def make_handoff(agent):
    return handoff(
        agent=agent,
        on_handoff=handle_handoff,
        input_type=HandoffData,
        input_filter=handoff_filters.remove_all_tools,
    )


triage_agent = Agent(
    name="Triage Agent",
    instructions=f"""
    {RECOMMENDED_PROMPT_PREFIX}

    You are the front desk greeter at our restaurant.

    YOUR ROLE: Understand what the customer needs and connect them to the right specialist.

    ROUTING RULES:
    - Menu questions (dishes, ingredients, allergies, dietary options) -> Menu Agent
    - Ordering food or drinks -> Order Agent
    - Table reservations (booking, changing, canceling) -> Reservation Agent

    BEHAVIOR:
    - Greet the customer warmly
    - Quickly identify their need
    - Hand off to the appropriate agent with a brief explanation
    - If unclear, ask a clarifying question before routing
    - Do NOT try to answer menu, order, or reservation questions yourself
    """,
    handoffs=[
        make_handoff(menu_agent),
        make_handoff(order_agent),
        make_handoff(reservation_agent),
    ],
)

if "session" not in st.session_state:
    st.session_state["session"] = SQLiteSession(
        "restaurant-bot-session",
        "restaurant-bot-memory.db",
    )
session = st.session_state["session"]


async def paint_history():
    messages = await session.get_items()

    for message in messages:
        if "role" in message:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.write(message["content"])
                else:
                    if message["type"] == "message":
                        st.write(message["content"][0]["text"].replace("$", "\\$"))


asyncio.run(paint_history())


def update_status(status_container, event_type):
    status_messages = {
        "response.completed": (" ", "complete"),
    }
    if event_type in status_messages:
        label, state = status_messages[event_type]
        status_container.update(label=label, state=state)


async def run_agent(message):
    with st.chat_message("ai"):
        status_container = st.status("Processing...", expanded=False)
        text_placeholder = st.empty()
        response = ""

        stream = Runner.run_streamed(
            triage_agent,
            message,
            session=session,
        )

        async for event in stream.stream_events():
            if event.type == "raw_response_event":
                update_status(status_container, event.data.type)

                if event.data.type == "response.output_text.delta":
                    response += event.data.delta
                    text_placeholder.write(response.replace("$", "\\$"))



prompt = st.chat_input("How can we help you today?")

if prompt:
    with st.chat_message("human"):
        st.write(prompt)
    asyncio.run(run_agent(prompt))


with st.sidebar:
    reset = st.button("Reset conversation")
    if reset:
        asyncio.run(session.clear_session())
        st.rerun()
