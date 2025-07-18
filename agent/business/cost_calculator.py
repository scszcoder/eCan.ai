model_pricing = {
    "OpenAI": {
        "gpt-4.1": {
            "input": 2.00,         # $ per 1M tokens
            "cached_input": 0.50,
            "output": 8.00
        },
        "gpt-4.1-mini": {
            "input": 0.40,
            "cached_input": 0.10,
            "output": 1.60
        },
        "gpt-4.1-nano": {
            "input": 0.10,
            "cached_input": 0.025,
            "output": 0.40
        },
        "o3": {
            "input": 2.00,
            "cached_input": 0.50,
            "output": 8.00
        },
        "o4-mini": {
            "input": 1.10,
            "cached_input": 0.275,
            "output": 4.40
        },
        "gpt-4o": {
            "input": 5.00,
            "cached_input": 2.50,
            "output": 20.00
        },
        "gpt-4o-mini": {
            "input": 0.60,
            "cached_input": 0.30,
            "output": 2.40
        },
    },
    # Add more vendors and models here
    "DeepSeek": {
        "deepseek-chat": {
            "input": 0.27,
            "cached_input": 0.07,
            "output": 1.10
        },
        "deepseek-reasoner": {
            "input": 0.55,
            "cached_input": 0.14,
            "output": 2.19
        },
        "deepseek-r1": {
            "input": 0.55,
            "output": 2.19
        },
        # For DeepSeek Coder, distinguish by model size
        "deepseek-coder-6.7b": {
            "input": 0.20,
            "output": 0.40
        },
        "deepseek-coder-33b": {
            "input": 1.00,
            "output": 2.00
        }
    }
}


def calculate_price(
        vendor,
        model,
        input_tokens=0,
        output_tokens=0,
        cached_input_tokens=0,
        price_db=model_pricing
):
    if vendor not in price_db or model not in price_db[vendor]:
        raise ValueError(f"Pricing for {vendor} {model} not found.")

    p = price_db[vendor][model]
    input_cost = (input_tokens / 1_000_000) * p.get("input", 0)
    cached_input_cost = (cached_input_tokens / 1_000_000) * p.get("cached_input", 0)
    output_cost = (output_tokens / 1_000_000) * p.get("output", 0)
    total = input_cost + cached_input_cost + output_cost
    return {
        "input_cost": input_cost,
        "cached_input_cost": cached_input_cost,
        "output_cost": output_cost,
        "total_cost": total
    }
