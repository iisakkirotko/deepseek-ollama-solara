# Setting up

1. Install Ollama from [here](https://ollama.com/download)
2. Run the model: `ollama pull deepseek-r1:8b`
3. Install this package: `(uv) pip install .`
4. Run the app: `solara run deepseek_ollama_solara.app`


## Using different models

If you want to use a different model, or have a number of models available, you can simply pull them using `ollama pull model`, and after a refresh the app should list the available models on the bottom of the sidebar.

## Tool calling

There are two model tools currently available to use - looking up articles on wikipedia and searching duckduckgo. Custom tools can be added by using `deepseek_ollama_solara.tools.add_tool`