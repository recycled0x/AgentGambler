from setuptools import setup, find_packages

setup(
    name="agent-gambler",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "web3>=6.0.0",
        "requests>=2.31.0",
        "python-dotenv>=1.0.0",
        "aiohttp>=3.9.0",
        "eth-account>=0.11.0",
        "click>=8.1.0",
        "rich>=13.0.0",
        "schedule>=1.2.0",
    ],
    entry_points={
        "console_scripts": [
            "agentgambler=agent_gambler.cli:main",
        ],
    },
    python_requires=">=3.10",
)
