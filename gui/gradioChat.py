
import threading
import gradio as gr
import random
import datetime
import asyncio

# Placeholder for chat history, bot list, and file handling
chat_history = {}
bots_list = ["Bot 1", "Bot 2", "Bot 3"]  # Example list of bots
current_bot = None


# Function to simulate receiving messages from the bot (or remote party)
def get_bot_message(user_name):
    messages = [
        "Hello, how can I assist you today?",
        "Here is some information you might find useful: https://example.com",
        "Please find the attached document."
    ]
    bot_msg = random.choice(messages)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"name": current_bot, "message": bot_msg, "timestamp": timestamp}


# Function to send a message
def send_message(message, chat_area):
    # Handle sending the message and appending to chat area
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    chat_area.append({"name": "You", "message": message, "timestamp": timestamp})

    # Simulate a response from the bot
    bot_message = get_bot_message(message)
    chat_area.append(bot_message)

    return chat_area, ""


# Function to handle file attachments
def attach_file(file, chat_area):
    if file is None:
        return chat_area, "No file attached."

    if current_bot is None:
        return chat_area, "Please select a bot from the phonebook."

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_msg = f"Sent a file: {file.name}"
    chat_area.append({"name": "You", "message": file_msg, "timestamp": timestamp})

    return chat_area, ""


# Function to handle switching bots from the phonebook
def switch_bot(bot_name):
    global current_bot
    current_bot = bot_name
    chat_history.setdefault(current_bot, [])
    return chat_history[current_bot], f"Switched to chat with {bot_name}"


# Function to dynamically switch between chat area and phonebook (bot list)
def show_phonebook():
    # Return bot list and message indicating phonebook is shown
    return gr.update(visible=False), gr.update(visible=True)


def show_chat():
    # Return chat area and message indicating chat is shown
    return gr.update(visible=True), gr.update(visible=False)


def launchChat(mwin):
    with gr.Blocks() as chat_app:
        with gr.Row():
            # Vertical Menu Bar
            with gr.Column(scale=1, min_width=50):
                chat_button = gr.Button("💬 Chat")
                phonebook_button = gr.Button("📖 Directory")
                settings_button = gr.Button("⚙️ Settings")
                search_button = gr.Button("🔍 Search")

            # Main Content Area (Chat and Phonebook will switch here)
            with gr.Column(scale=4):
                # Chat Area
                chat_area = gr.Chatbot(label="Chat", height=400, visible=True)
                message_input = gr.Textbox(placeholder="Type your message here...")
                submit_button = gr.Button("Send")
                file_upload = gr.File(label="Attach File", file_types=["file"])
                output_message = gr.Textbox(label="Status", interactive=False)

                # Phonebook (List of Bots)
                bot_selection = gr.Dropdown(choices=bots_list, label="Select Bot", visible=False)

        # Chat Actions
        submit_button.click(send_message, inputs=[message_input, chat_area], outputs=[chat_area, output_message])
        file_upload.upload(attach_file, inputs=[file_upload, chat_area], outputs=[chat_area, output_message])

        # Phonebook actions
        phonebook_button.click(show_phonebook, outputs=[chat_area, bot_selection])
        chat_button.click(show_chat, outputs=[chat_area, bot_selection])
        bot_selection.change(switch_bot, inputs=[bot_selection], outputs=[chat_area, output_message])


    chat_app.launch()

# http://127.0.0.1:7860 is the port for chat.
async def start_gradio_chat_in_background(mwin):
    # Run Gradio launch in a background thread
    await asyncio.to_thread(launchChat(mwin))