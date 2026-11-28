"""Railway project for the cascade. Neon is the database. No database plugin."""

from railway_sdk import define_railway, image, preserve, project, service

def _private(name: str) -> str:
    return "http://${{" + name + ".RAILWAY_PRIVATE_DOMAIN}}:${{" + name + ".PORT}}"


@define_railway
def main(ctx=None):
    toolbox = service(
        "mcp-toolbox",
        build={"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile.toolbox"},
        start="node scripts/start-toolbox.mjs",
        healthcheck="/",
        env={
            "PORT": "5000",
            "DATABASE_URL": preserve(),
        },
    )
    judge = service(
        "a2a-judge",
        build={"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"},
        start="python -m src.a2a.run_servers",
        healthcheck="/.well-known/agent.json",
        env={
            "A2A_ONLY": "judge",
            "HOST": "0.0.0.0",
            "PORT": "10002",
            "GOOGLE_API_KEY": preserve(),
        },
    )
    masker = service(
        "a2a-masker",
        build={"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"},
        start="python -m src.a2a.run_servers",
        healthcheck="/.well-known/agent.json",
        env={
            "A2A_ONLY": "masker",
            "HOST": "0.0.0.0",
            "PORT": "10003",
        },
    )
    phoenix = service(
        "phoenix",
        source=image("arizephoenix/phoenix:version-22.0.1"),
        healthcheck="/",
        env={
            "PORT": "6006",
            "PHOENIX_ENABLE_AUTH": "true",
            "PHOENIX_SECRET": preserve(),
        },
    )
    web = service(
        "web-voice-app",
        build={"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"},
        start="python -m src.api.web",
        healthcheck="/",
        env={
            "HOST": "0.0.0.0",
            "DATABASE_URL": preserve(),
            "GOOGLE_API_KEY": preserve(),
            "MEM0_API_KEY": preserve(),
            "TOOLBOX_URL": _private("mcp-toolbox"),
            "A2A_JUDGE_HOST": "${{a2a-judge.RAILWAY_PRIVATE_DOMAIN}}",
            "A2A_JUDGE_PORT": "${{a2a-judge.PORT}}",
            "A2A_MASK_HOST": "${{a2a-masker.RAILWAY_PRIVATE_DOMAIN}}",
            "A2A_MASK_PORT": "${{a2a-masker.PORT}}",
            "PHOENIX_URL": _private("phoenix"),
            "PHOENIX_PUBLIC_URL": "https://${{phoenix.RAILWAY_PUBLIC_DOMAIN}}",
            "PHOENIX_API_KEY": preserve(),
            "TELEMETRY": "true",
            "MASK": "true",
        },
    )
    return project(
        "customer-support-voice-agent",
        resources=[toolbox, judge, masker, phoenix, web],
    )
