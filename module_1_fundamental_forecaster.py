import google.generativeai as genai
from google.generativeai.types import GenerationConfig
from langchain_community.utilities import GoogleSerperAPIWrapper
from langchain_community.document_loaders import WebBaseLoader
from langchain.tools import tool
from langchain_community.agents import create_react_agent
from langchain.agents import AgentExecutor
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain import hub

import config
import json

# --- Define Agent Tools ---

@tool
def scrape_webpage(url: str) -> str:
    """
    Scrapes the text content of a single webpage given its URL.
    Input must be a valid URL. Used to get deep context from a search result.
    """
    #
    print(f"--- Scraping URL: {url} ---")
    try:
        loader = WebBaseLoader(url)
        docs = loader.load()
        content = docs.page_content
        # Truncate to first 4000 chars to avoid overwhelming the context window
        return content[:4000]
    except Exception as e:
        return f"Error scraping URL {url}: {e}"

class FundamentalForecaster:
    """
    Module 1: The "Agentic RAG Brain".
    This module uses a ReAct agent to perform "deep research" on the web.
    It searches, scrapes, and summarizes info to build a context, then
    feeds that context into the "Alphascope" prompt for a final probability.
    """
    def __init__(self):
        # 1. Init Gemini LLM for the final "Forecaster" step 
        genai.configure(api_key=config.GEMINI_API_KEY)
        self.forecaster_llm = genai.GenerativeModel('gemini-1.5-flash')
        
        # 2. Init a separate LangChain-compatible LLM for the "Research Agent" [22, 25]
        self.agent_llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash", 
            temperature=0, 
            convert_system_message_to_human=True,
            google_api_key=config.GEMINI_API_KEY
        )
        
        # 3. Define the tools for the Research Agent
        search_tool = GoogleSerperAPIWrapper(serper_api_key=config.SERPER_API_KEY, k=5) #
        search_tool.name = "web_search"
        search_tool.description = "Searches the web for recent news and information. Input is a search query."
        
        self.tools = [search_tool, scrape_webpage]
        
        # 4. Create the ReAct Agent
        # Pull the standard ReAct prompt template
        react_prompt = hub.pull("hwchase17/react")
        
        # Create the agent
        agent = create_react_agent(self.agent_llm, self.tools, react_prompt)
        
        # Create the agent executor (the runtime for the agent)
        self.agent_executor = AgentExecutor(
            agent=agent, 
            tools=self.tools, 
            verbose=True,
            handle_parsing_errors=True # Crucial for reliability
        )
        print("Module 1: 'Deep Research' agent initialized.")

    def _perform_web_research(self, market_question: str) -> str:
        """
        Runs the full agentic research pipeline.
        Returns a string of "Retrieved Info" for the Alphascope prompt.
        """
        print(f"--- Module 1: Starting 'Deep Research' for: {market_question} ---")
        
        # This prompt guides the agent's entire thinking process
        agent_prompt = f"""
        You are a world-class political research analyst. Your goal is to find
        the most critical, factual, and recent information to help an analyst
        assign a probability to the following prediction market question.

        Market Question: '{market_question}'

        Your process is:
        1.  Formulate 2-3 search queries to find the *most recent* (last 48 hours)
            and *factual* (polls, reports, official statements) information.
        2.  Execute the 'web_search' tool with your queries.
        3.  Review the search snippets. Identify the top 2-3 *most relevant* URLs.
        4.  Use the 'scrape_webpage' tool on each of those 2-3 URLs.
        5.  Read all the scraped content.
        6.  Synthesize all the facts, polls, and key information you've found into
            a single, concise summary. This summary will be used as the *only*
            context for a final probability forecast.

        Begin your work.
        """
        
        try:
            # Invoke the agent and let it run (search, scrape, summarize)
            agent_result = self.agent_executor.invoke({"input": agent_prompt})
            research_summary = agent_result['output']
            print(f"--- Module 1: 'Deep Research' complete. Context acquired. ---")
            return research_summary
        except Exception as e:
            print(f"Error during agentic research: {e}")
            return "Research agent failed to find information."


    def _build_prompt(self, market_question: str, market_rules: str, context: str) -> str:
        """Builds the final "Alphascope" prompt, identical to your example."""
        return f"""
        You are an expert political analyst and forecaster. Your task is to provide a precise, numerical probability for a specific event based ONLY on the real-time context provided.

        **Event Market:**
        Question: {market_question}
        Resolution Criteria: {market_rules}

        **Retrieved Real-Time Context (from 'Deep Research' Agent):**
        ---
        {context}
        ---

        **Task:**
        Analyze the provided context. Determine the probability of the event occurring (resolving "Yes"). Provide a brief rationale, citing the most relevant context.

        Respond ONLY in the following JSON format:
        {{
          "reasoning": "A brief 1-2 sentence rationale for your decision.",
          "probability": <float between 0.00 and 1.00>
        }}
        """

    def get_fundamental_probability(self, market: Market) -> float:
        """
        The main public method for Module 1.
        Returns a single, fundamentally-derived probability.
        """
        print(f"Module 1: Running Agentic RAG analysis for {market.ticker}...")
        try:
            # 1. Run the agent to get context
            market_question = market.title
            context = self._perform_web_research(market_question)
            
            # 2. Build the "Alphascope" prompt
            prompt = self._build_prompt(market_question, market.rules, context)
            
            # 3. Call Gemini (Forecaster) with
            #    Structured Output (JSON Mode)
            json_config = GenerationConfig(response_mime_type="application/json")
            response = self.forecaster_llm.generate_content(prompt, generation_config=json_config)
            
            # 4. Parse response
            result = json.loads(response.text)
            probability = float(result.get('probability', 0.5)) # Default to 0.5 on error
            print(f"Module 1: Gemini forecast complete. Prob: {probability:.2f}. Reasoning: {result.get('reasoning')}")
            
            return probability
        except Exception as e:
            print(f"Error in Module 1 (Gemini Forecaster): {e}")
            return 0.5 # Return neutral probability on failure
