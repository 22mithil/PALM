import asyncio
from app.integrations.fastrouter.llm import generate_response

async def run():
    res1 = await generate_response("Write a story around 50 words about a brave frog.")
    print("RES1:", res1)

if __name__ == "__main__":
    asyncio.run(run())
