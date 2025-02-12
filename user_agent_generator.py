from latest_user_agents import get_latest_user_agents
from fake_useragent import UserAgent
from user_agent import generate_user_agent

def generate_unique_uas():
    """ this function combines a few modules to generate a list of unique uas """
    
    unique_user_agents = set(get_latest_user_agents())
    ua = UserAgent()
    
    while len(unique_user_agents) < 1000:
        unique_user_agents.add(ua.random)
        unique_user_agents.add(generate_user_agent())
    return list(unique_user_agents)
