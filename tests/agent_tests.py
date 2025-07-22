from agent.ec_agent import *
import asyncio


SEARCH_PARTS_RESULTS = {
  "id": "1110",
  "title": "MCU Search Results",
  "Items": [
    {
      "product_id": "0101",
      "product_name": "8bit MCU",
      "brand": "Microchip",
      "model": "AVR16EB14",
      "main_image": "https://media.microchip.com/silicon-devices/medium/avr16eb14-d3x.png",
      "url": "https://www.microchip.com/en-us/product/AVR16EB14",
      "rank": 1,
      "score": 99.01,
      "highlights": [
        { "label": "size", "value": "0201", "unit": "size" },
        { "label": "price", "value": "0.01", "unit": "size" },
        { "label": "precision", "value": "100", "unit": "ppm" }
      ],
      "app_specific": [
        {
          "app": "oil_diffuser",
          "needed_criterias": [
            {
              "criteria1": "spec1",
              "required_value": "100",
              "matched_value": "120"
            }
          ]
        }
      ]
    },
    {
      "product_id": "0111",
      "product_name": "8bit MCU",
      "brand": "Microchip",
      "model": "PIC16F18175",
      "main_image": "https://media.microchip.com/silicon-devices/medium/pic16f18175-s2x.png",
      "url": "https://www.microchip.com/en-us/product/PIC16F18175",
      "rank": 2,
      "score": 98.01,
      "highlights": [
        { "label": "size", "value": "0201", "unit": "size" },
        { "label": "price", "value": "0.01", "unit": "size" },
        { "label": "precision", "value": "100", "unit": "ppm" }
      ],
      "app_specific": [
        {
          "app": "oil_diffuser",
          "needed_criterias": [
            {
              "criteria1": "spec1",
              "required_value": "100",
              "matched_value": "120"
            }
          ]
        }
      ]
    },
    {
      "product_id": "0112",
      "product_name": "8bit MCU",
      "brand": "Silicon Labs",
      "model": "C8051F060",
      "main_image": "https://silabs.scene7.com/is/image/siliconlabs/qfp100?$TransparentPNG$",
      "url": "https://www.silabs.com/mcu/8-bit-microcontrollers/c8051f06x/device.c8051f060?tab=specs",
      "rank": 3,
      "score": 96.01,
      "highlights": [
        { "label": "size", "value": "0201", "unit": "size" },
        { "label": "price", "value": "0.01", "unit": "size" },
        { "label": "precision", "value": "100", "unit": "ppm" }
      ],
      "app_specific": [
        {
          "app": "oil_diffuser",
          "needed_criterias": [
            {
              "criteria1": "spec1",
              "required_value": "100",
              "matched_value": "120"
            }
          ]
        }
      ]
    }
  ],
  "summary": {
    "AVR16EB14": {
      "Clock Speed": "16 MHz",
      "I/Os": "16",
      "RAM": "1KB"
    },
    "PIC16F18175": {
      "Clock Speed": "20 MHz",
      "I/Os": "12",
      "RAM": "1KB"
    },
    "C8051F060": {
      "Clock Speed": "20 MHz",
      "I/Os": "14",
      "RAM": "4KB"
    }
  },
  "comments": ["After extensive search, we found these parts to be the best matches for your intended use."],
  "statistics": {
    "sites_visited": 3,
    "searches": 3,
    "pages_visited": 1,
    "input_tokens": 1,
    "output_tokens": 1,
    "products_compared": 1
  },
  "behind_the_scene": "",
  "show_feedback_options": True
}

# test agent capabilities in a variety of ways.
# for now only test use_vision, and no test for playwright
async def test_helper(mwin):
    # create a a2a_client, test a2a.
    print("# agents....", len(mwin.agents))
    helper = next((ag for ag in mwin.agents if ag and "helper" in ag.card.name), None)

    if helper:
        helper_card = helper.get_card()

        test_a2a_client = A2AClient(helper_card)

        payload = {
            "id": "task-001",
            "sessionId": "sess-abc",
            "message": Message(role="user", parts=[TextPart(type="text", text="Summarize this report")]),
            "acceptedOutputModes": ["json"],
            "skill": "resolve_rpa_failure"  # Or whatever your agent expects
        }
        # send a say message to helper agent
        response = await test_a2a_client.send_task(payload)

        if response:
            print('\n--------------------------------')
            print('a2a  result:', response)
            # print(f'Platform:         {profile.platform}')

        else:
            print('No result')


        # create a MCP client to test mcp server.
        reponse = await helper.skills[0].runnable.ainvoke({"messages": "say hello to me"})
        print(response)
