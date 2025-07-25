import google.generativeai as genai
from .llm import LLM
from .config import load_config
import json

class Google(LLM):
    """A class for interacting with Google's Generative AI."""

    def __init__(self, tools=None, verbose=False, project_root=None):
        config = load_config()
        api_key = config.get('GOOGLE_API_KEY')
        if not api_key:
            raise ValueError('GOOGLE_API_KEY not found in config')
        genai.configure(api_key=api_key)
        self.tools = tools or []
        self.verbose = verbose
        self.project_root = project_root
        
        # Initialize model - simplified approach without function calling for now
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    def _enhance_prompt_with_tools(self, prompt):
        """Enhance the prompt with tool usage instructions."""
        if not self.tools:
            return prompt
        
        tool_descriptions = []
        for tool in self.tools:
            # Access tool attributes instead of dictionary keys
            tool_name = getattr(tool, 'name', str(tool.__class__.__name__))
            tool_desc = getattr(tool, 'description', f'Tool: {tool_name}')
            tool_descriptions.append(f"- {tool_name}: {tool_desc}")
        
        enhanced_prompt = f"""{prompt}

Você tem acesso às seguintes ferramentas:
{chr(10).join(tool_descriptions)}

Para usar uma ferramenta, responda no formato:
USE_TOOL: nome_da_ferramenta
PARAMS: {{"parametro": "valor"}}

Se não precisar usar ferramentas, responda normalmente."""
        
        return enhanced_prompt

    def _process_response_with_tools(self, response_text, original_prompt):
        """Process the response and execute any tool commands found."""
        import re
        
        # Look for tool usage pattern
        tool_pattern = r'USE_TOOL:\s*(\w+)\s*\nPARAMS:\s*({.*?})'
        matches = re.findall(tool_pattern, response_text, re.DOTALL)
        
        if matches:
            for tool_name, params_str in matches:
                try:
                    try:
                        params = json.loads(params_str)
                    except json.JSONDecodeError as e:
                        if 'Unterminated string' in str(e) or 'Invalid control character' in str(e):
                            # Try to fix the string by escaping newlines and re-parsing
                            fixed_params_str = params_str.replace('\n', '\\n')
                            params = json.loads(fixed_params_str)
                        else:
                            raise # Re-raise other JSON errors

                    tool_result = self._execute_tool(tool_name, params)
                    
                    # Replace the tool call with the result in the response
                    tool_call_text = f"USE_TOOL: {tool_name}\nPARAMS: {params_str}"
                    response_text = response_text.replace(tool_call_text, f"[Ferramenta {tool_name} executada: {tool_result}]")
                    
                except Exception as e:
                    if self.verbose:
                        print(f"Error executing tool {tool_name}: {e}")
        
        # Create a mock response object
        class MockResponse:
            def __init__(self, text):
                self.text = text
        
        return MockResponse(response_text)

    def _execute_tool(self, tool_name, params):
        """Execute a tool with given parameters."""
        for tool in self.tools:
            current_tool_name = getattr(tool, 'name', str(tool.__class__.__name__))
            if current_tool_name == tool_name:
                if hasattr(tool, 'use'):
                    # If it's the python tool, inject the working directory
                    if tool_name == 'python':
                        # The 'python' tool expects a 'code' parameter and an optional 'working_directory'
                        code_to_execute = params.get('code')
                        if code_to_execute:
                            tool_params = {'code': code_to_execute}
                            if self.project_root:
                                tool_params['working_directory'] = self.project_root
                            return tool.use(**tool_params)
                        else:
                            return 'Error: code parameter not found for python tool.'
                    return tool.use(**params)
                elif hasattr(tool, 'execute'):
                    return tool.execute(**params)
                elif callable(tool):
                    return tool(**params)
        
        return f"Tool {tool_name} not found or not executable"

    def complete(self, prompt, **kwargs):
        """Generate a completion for a given prompt."""
        try:
            if self.verbose:
                print(f"Google Gemini processing prompt: {prompt[:100]}...")
            
            # Enhanced prompt to include tool usage instructions
            enhanced_prompt = self._enhance_prompt_with_tools(prompt)
            
            response = self.model.generate_content(enhanced_prompt, **kwargs)
            
            # Process the response and execute any tool commands found
            response_text = "".join([part.text for part in response.parts])
            if response_text:
                return self._process_response_with_tools(response_text, prompt)
            
            return response
            
        except Exception as e:
            if self.verbose:
                print(f"Error in Google completion: {e}")
            raise e


