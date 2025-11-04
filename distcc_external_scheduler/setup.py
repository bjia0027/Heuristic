#!/usr/bin/env python3
"""
Distcc 外部调度器安装脚本
"""

from setuptools import setup, find_packages
import os

# 读取README文件
def read_file(filename):
    with open(os.path.join(os.path.dirname(__file__), filename), encoding='utf-8') as f:
        return f.read()

# 读取requirements
def read_requirements():
    with open('requirements.txt') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name="distcc-external-scheduler",
    version="1.0.0",
    description="Distcc 外部独立调度器",
    long_description=read_file("README.md"),
    long_description_content_type="text/markdown",
    
    author="AI Assistant",
    author_email="",
    
    url="https://github.com/your-org/distcc-external-scheduler",
    
    packages=find_packages(),
    include_package_data=True,
    
    python_requires=">=3.8",
    
    install_requires=read_requirements(),
    
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'pytest-asyncio>=0.21.0',
            'pytest-cov>=4.0.0',
            'black>=22.0.0',
            'flake8>=5.0.0',
            'mypy>=1.0.0',
        ],
        'visualization': [
            'matplotlib>=3.6.0',
            'graphviz>=0.20.0',
        ]
    },
    
    entry_points={
        'console_scripts': [
            'distcc-scheduler=scheduler_main:main',
            'distcc-scheduler-client=client_example:main',
            'distcc-scheduler-benchmark=tools.benchmark:main',
        ],
    },
    
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9", 
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Build Tools",
        "Topic :: System :: Distributed Computing",
    ],
    
    keywords="distcc distributed compilation scheduling build-tools",
    
    project_urls={
        "Documentation": "https://github.com/your-org/distcc-external-scheduler/wiki",
        "Source": "https://github.com/your-org/distcc-external-scheduler",
        "Tracker": "https://github.com/your-org/distcc-external-scheduler/issues",
    },
) 