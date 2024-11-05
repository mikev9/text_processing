import uvicorn

from shared.config import web_api_config

from web_api.app import app


if __name__ == '__main__':
    uvicorn_config = uvicorn.Config(
        app=app,
        host=web_api_config.web_api_host,
        port=web_api_config.web_api_port,
    )
    server = uvicorn.Server(uvicorn_config)
    server.run()
