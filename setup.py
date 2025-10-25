#!/usr/bin/env python3
"""Setup script for Stockshot Browser."""

from setuptools import setup, find_packages
import os

# Read the README file
def read_readme():
    readme_path = os.path.join(os.path.dirname(__file__), 'README.md')
    if os.path.exists(readme_path):
        with open(readme_path, 'r', encoding='utf-8') as f:
            return f.read()
    return "Stockshot Browser - Professional video file explorer for industry workflows"

# Read requirements
def read_requirements():
    requirements_path = os.path.join(os.path.dirname(__file__), 'requirements.txt')
    with open(requirements_path, 'r', encoding='utf-8') as f:
        requirements = []
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                # Remove version constraints for setup.py
                package = line.split('>=')[0].split('==')[0].split('<')[0]
                requirements.append(package)
        return requirements

setup(
    name="stockshot-browser",
    version="1.0.0",
    author="Stockshot Team",
    author_email="team@stockshot.com",
    description="Professional video file explorer for industry workflows",
    long_description=read_readme(),
    long_description_content_type="text/markdown",
    url="https://github.com/stockshot/stockshot-browser",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Video",
        "Topic :: System :: Filesystems",
    ],
    python_requires=">=3.8",
    install_requires=read_requirements(),
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-qt>=4.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "stockshot-browser=stockshot_browser.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "stockshot_browser": [
            "resources/icons/*.png",
            "resources/icons/*.svg",
            "resources/styles/*.qss",
            "resources/config_templates/*.json",
        ],
    },
)