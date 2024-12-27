import os
import json
import time
import requests
import aiohttp
import runpod

def wait_for_service(url, max_retries=1000, delay=0.5):
    retries = 0
    while retries < max_retries:
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return
            else:
                print(f"Service status code: {response.status_code}. Retrying...")
        except requests.exceptions.RequestException:
            print("Service not ready yet. Retrying...")
        time.sleep(delay)
        retries += 1
    raise Exception("Service not available after max retries.")

class JobInput:
    def __init__(self, job_input):
        self.openai_route = job_input.get('openai_route')
        self.openai_input = job_input.get('openai_input')
        self.method = job_input.get('method', 'POST')
        self.headers = job_input.get('headers', {})

class OpenAITabbyEngine:
    def __init__(self, base_url='http://127.0.0.1:5000'):
        self.base_url = base_url

    async def generate(self, job_input):
        route = job_input.openai_route
        data = job_input.openai_input
        method = job_input.method.upper()
        headers = job_input.headers or {}

        # Map the route to the correct TabbyAPI endpoint and method
        if route in ['/v1/models', '/v1/model/list']:
            # GET request to list models
            async for response in self._handle_generic_request('/v1/model/list', None, 'GET', headers):
                yield response
        elif route == '/v1/model':
            # GET request to get the current model
            async for response in self._handle_generic_request('/v1/model', None, 'GET', headers):
                yield response
        elif route == '/v1/auth/permission':
            # GET request to get permission
            async for response in self._handle_generic_request('/v1/auth/permission', None, 'GET', headers):
                yield response
        elif route in ['/v1/token/encode', '/v1/token/decode']:
            # POST request for token encode/decode
            async for response in self._handle_generic_request(route, data, 'POST', headers):
                yield response
        elif route in ['/v1/completions', '/v1/chat/completions', '/v1/embeddings']:
            # Handle generation requests
            async for response in self._handle_generation_request(route, data, headers):
                yield response
        else:
            yield {"error": f"Unsupported route: {route}"}

    async def _handle_generic_request(self, route, data=None, method='GET', headers=None):
        endpoint = self.base_url + route
        async with aiohttp.ClientSession() as session:
            try:
                if method == 'GET':
                    async with session.get(endpoint, headers=headers, timeout=300) as response:
                        if response.status != 200:
                            yield {"error": await response.text()}
                            return
                        result = await response.json()
                        yield result
                elif method == 'POST':
                    async with session.post(endpoint, json=data, headers=headers, timeout=300) as response:
                        if response.status != 200:
                            yield {"error": await response.text()}
                            return
                        result = await response.json()
                        yield result
                else:
                    yield {"error": f"Unsupported HTTP method: {method}"}
            except Exception as e:
                yield {"error": str(e)}

    async def _handle_generation_request(self, route, data, headers):
        endpoint = self.base_url + route
        stream = data.get('stream', False)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(endpoint, json=data, headers=headers, timeout=300) as response:
                    if response.status != 200:
                        error_json = json.dumps({"error": await response.text()})
                        yield f"{error_json}\n"  # Removed 'data: ' prefix
                        return

                    if stream:
                        async for line in response.content:
                            try:
                                decoded_line = line.decode('utf-8').strip()
                                if decoded_line:
                                    yield f"{decoded_line}\n"  # Removed 'data: ' prefix
                            except Exception as e:
                                error_json = json.dumps({"error": f"Failed to decode stream data: {str(e)}"})
                                yield f"{error_json}\n"  # Removed 'data: ' prefix
                        # End of stream
                        yield "[DONE]\n"  # Removed 'data: ' prefix
                    else:
                        result = await response.json()
                        yield f"{json.dumps(result)}\n"  # Removed 'data: ' prefix
            except Exception as e:
                error_json = json.dumps({"error": str(e)})
                yield f"{error_json}\n"  # Removed 'data: ' prefix

async def handler(job):
    job_input = JobInput(job['input'])
    if not job_input.openai_route or not isinstance(job_input.openai_input, (dict, type(None))):
        yield {"error": "Invalid input: missing 'openai_route' or 'openai_input' must be a dictionary or None"}
        return

    engine = OpenAITabbyEngine()

    async for output in engine.generate(job_input):
        yield output

if __name__ == "__main__":
    try:
        wait_for_service('http://127.0.0.1:5000/health')
    except Exception as e:
        print("Service failed to start:", str(e))
        exit(1)

    print("TabbyAPI Service is ready. Starting RunPod...")

    runpod.serverless.start(
        {
            "handler": handler,
            "return_aggregate_stream": True,
        }
    )