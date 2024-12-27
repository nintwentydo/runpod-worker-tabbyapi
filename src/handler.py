import os
import json
import time
import requests
import aiohttp
import runpod
import asyncio
import atexit
import logging
from collections import deque

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize a global aiohttp ClientSession
session = aiohttp.ClientSession()

async def close_session():
    await session.close()

# Register the close_session coroutine to run on exit
atexit.register(lambda: asyncio.get_event_loop().run_until_complete(close_session()))

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
            yield json.dumps({"error": f"Unsupported route: {route}"}) + "\n"

    async def _handle_generic_request(self, route, data=None, method='GET', headers=None):
        endpoint = self.base_url + route
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
        try:
            async with session.post(endpoint, json=data, headers=headers, timeout=300) as response:
                if response.status != 200:
                    error_json = json.dumps({"error": await response.text()})
                    yield f"{error_json}\n\n"  # No 'data: ' prefix
                    return

                if stream:
                    async for line in response.content:
                        try:
                            decoded_line = line.decode('utf-8').strip()
                            if decoded_line:
                                yield f"{decoded_line}\n\n"  # No 'data: ' prefix
                        except Exception as e:
                            error_json = json.dumps({"error": f"Failed to decode stream data: {str(e)}"})
                            yield f"{error_json}\n\n"  # No 'data: ' prefix
                    # Removed: yield "[DONE]\n"  # Let RunPod handle it
                else:
                    result = await response.json()
                    yield f"{json.dumps(result)}\n\n"  # No 'data: ' prefix
        except Exception as e:
            error_json = json.dumps({"error": str(e)})
            yield f"{error_json}\n\n"  # No 'data: ' prefix

async def async_generator_handler(job):
    job_input = JobInput(job['input'])
    if not job_input.openai_route or not isinstance(job_input.openai_input, (dict, type(None))):
        yield json.dumps({"error": "Invalid input: missing 'openai_route' or 'openai_input' must be a dictionary or None"}) + "\n\n"
        return

    engine = OpenAITabbyEngine()

    async for output in engine.generate(job_input):
        # Ensure that only JSON strings are yielded without 'data: ' prefixes
        if isinstance(output, dict):
            # Convert dict to JSON string
            yield json.dumps(output) + "\n\n"
        else:
            # If output is already a JSON string, ensure it ends with double newline
            yield f"{output}\n\n"

# Initialize request rate tracking
request_timestamps = deque()

def update_request_rate():
    """
    Implement a method to accurately track the request rate.
    Using a sliding window of 60 seconds.
    """
    global request_rate
    current_time = time.time()
    window_start = current_time - 60  # 60-second window

    # Remove timestamps older than the window
    while request_timestamps and request_timestamps[0] < window_start:
        request_timestamps.popleft()

    # This function should be called at the start of each request
    # For demonstration, we'll simulate by incrementing
    request_timestamps.append(current_time)

    # Update the global request rate
    request_rate = len(request_timestamps)

def adjust_concurrency(current_concurrency):
    """
    Dynamically adjusts the concurrency level based on the observed request rate.
    """
    global request_rate
    update_request_rate()  # Update 'request_rate'

    max_concurrency = 10  # Maximum allowable concurrency
    min_concurrency = 1   # Minimum concurrency to maintain
    high_request_rate_threshold = 50  # Threshold for high request volume

    # Increase concurrency if under max limit and request rate is high
    if (request_rate > high_request_rate_threshold and current_concurrency < max_concurrency):
        return current_concurrency + 1
    # Decrease concurrency if above min limit and request rate is low
    elif (request_rate <= high_request_rate_threshold and current_concurrency > min_concurrency):
        return current_concurrency - 1

    return current_concurrency

if __name__ == "__main__":
    try:
        wait_for_service('http://127.0.0.1:5000/health')
    except Exception as e:
        print("Service failed to start:", str(e))
        exit(1)

    print("TabbyAPI Service is ready. Starting RunPod...")

    runpod.serverless.start(
        {
            "handler": async_generator_handler,         # Use the asynchronous handler
            "concurrency_modifier": adjust_concurrency, # Add the concurrency modifier
            "return_aggregate_stream": False,          # As per your working configuration
        }
    )