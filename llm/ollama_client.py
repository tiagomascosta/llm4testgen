import requests
from requests.exceptions import HTTPError, ConnectionError, Timeout
from typing import Dict, Any, Optional, List
import logging
import time
import json

logger = logging.getLogger(__name__)

class OllamaClient:
    """Client for communicating with Ollama API with robust error handling and retries."""
    
    def __init__(
        self,
        base_url: str,
        code_model: str,
        non_code_model: str,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        timeout: int = 90,
        json_logger=None
    ):
        """
        Initialize the Ollama client.
        
        Args:
            base_url: The base URL for the Ollama API
            code_model: The model to use for code-related tasks
            non_code_model: The model to use for non-code tasks (e.g. scenarios)
            max_retries: Maximum number of retries for failed requests
            retry_delay: Delay between retries in seconds
            timeout: Request timeout in seconds
            json_logger: Optional TestGenerationLogger instance for tracking metrics
        """
        self.base_url = base_url
        self.code_model = code_model
        self.non_code_model = non_code_model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.json_logger = json_logger
        self.request_count = 0
        self.total_response_time = 0.0

    def _is_reasoning_model(self, model: str) -> bool:
        """
        Check if the given model is a reasoning model that supports the 'think' parameter.
        
        Args:
            model: Model name to check
            
        Returns:
            True if the model is a reasoning model (currently deepseek-r1 variants)
        """
        return model.startswith("deepseek-r1")

    def _make_request(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        is_code_task: bool = True,
        attempt: int = 1
    ) -> str:
        """
        Make a request to Ollama with retries and error handling.
        
        Args:
            messages: List of message dictionaries
            model: Optional model override
            schema: Optional JSON schema for structured output
            is_code_task: Whether this is a code-related task (uses code_model) or not (uses non_code_model)
            attempt: Current attempt number (for retries)
            
        Returns:
            The response content as a string
            
        Raises:
            RuntimeError: If all retries fail
        """
        # Start timing this request
        request_start_time = time.time()
        
        # Choose model based on task type if not explicitly provided
        chosen_model = model or (self.code_model if is_code_task else self.non_code_model)
        
        # Check if this is a reasoning model
        is_reasoning = self._is_reasoning_model(chosen_model)
        
        base_payload = {
            "model": chosen_model,
            "messages": messages,
            "stream": False,
            "options": {
                "num_ctx": 32000,
            }
        }
        
        # Enable reasoning for reasoning models
        if is_reasoning:
            base_payload["think"] = True
            logger.info(f"Using reasoning model {chosen_model} with think parameter enabled")
        
        # Add schema if provided
        payload = {**base_payload, "format": schema} if schema else base_payload
        
        try:
            resp = requests.post(self.base_url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            content = resp.json().get("message", {}).get("content", "")
            
            # Calculate response time for this request
            response_time = time.time() - request_start_time
            self.total_response_time += response_time
            
            # Count every request (including retries)
            self.request_count += 1
            
            # Check if response was truncated
            if content and content.endswith('...'):
                logger.warning("Response appears to be truncated, retrying with larger context...")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    return self._make_request(messages, model, schema, is_code_task, attempt + 1)
                else:
                    raise RuntimeError("Response was truncated and max retries exceeded")
            
            # If we got an empty response and have retries left, try again
            if not content and attempt < self.max_retries:
                logger.debug(f"Empty response received, retrying (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(self.retry_delay)
                return self._make_request(messages, model, schema, is_code_task, attempt + 1)
            
            return content
            
        except ConnectionError as e:
            # Calculate response time even for failed requests
            response_time = time.time() - request_start_time
            self.total_response_time += response_time
            
            # Count failed requests too
            self.request_count += 1
            
            if attempt < self.max_retries:
                logger.debug(f"Connection failed, retrying (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(self.retry_delay)
                return self._make_request(messages, model, schema, is_code_task, attempt + 1)
            else:
                raise RuntimeError() from e
        except (HTTPError, Timeout) as e:
            # Calculate response time even for failed requests
            response_time = time.time() - request_start_time
            self.total_response_time += response_time
            
            # Count failed requests too
            self.request_count += 1
            
            if attempt < self.max_retries:
                logger.debug(f"Request failed, retrying (attempt {attempt + 1}/{self.max_retries})")
                time.sleep(self.retry_delay)
                return self._make_request(messages, model, schema, is_code_task, attempt + 1)
            else:
                raise RuntimeError() from e

    def call_structured(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        model: Optional[str] = None,
        is_code_task: bool = True
    ) -> str:
        """
        Make a structured request to Ollama with schema validation.
        
        Args:
            messages: List of message dictionaries
            schema: JSON schema for structured output
            model: Optional model override
            is_code_task: Whether this is a code-related task (uses code_model) or not (uses non_code_model)
            
        Returns:
            The response content as a string
            
        Raises:
            RuntimeError: If all retries fail
        """
        attempt = 1
        while attempt <= self.max_retries:
            try:
                content = self._make_request(messages, model, schema, is_code_task)
                
                # First try to parse as JSON
                try:
                    json_content = json.loads(content)
                    # If we get here, the JSON is valid
                    return content
                except json.JSONDecodeError as e:
                    if attempt >= self.max_retries:
                        raise RuntimeError(f"Failed to get valid JSON after {self.max_retries} attempts") from e
                    time.sleep(self.retry_delay)
                    attempt += 1
                    continue
                        
            except Exception as e:
                if attempt >= self.max_retries:
                    raise RuntimeError(f"Failed after {self.max_retries} attempts") from e
                time.sleep(self.retry_delay)
                attempt += 1
                continue

    def call_unstructured(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        is_code_task: bool = True
    ) -> str:
        """
        Make an unstructured request to Ollama.
        
        Args:
            messages: List of message dictionaries
            model: Optional model override
            is_code_task: Whether this is a code-related task (uses code_model) or not (uses non_code_model)
            
        Returns:
            The response content as a string
            
        Raises:
            RuntimeError: If all retries fail
        """
        return self._make_request(messages, model, None, is_code_task)
    
    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current LLM metrics.
        
        Returns:
            Dictionary with request count and total response time
        """
        return {
            "request_count": self.request_count,
            "total_response_time": self.total_response_time
        } 