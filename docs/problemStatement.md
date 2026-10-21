# Problem Statement

## Project Context

**DineMate** is an AI-powered restaurant recommendation service inspired by Zomato. The project lives in this repository (`ai-restaurant-dinemate`) and is intended to help users discover restaurants that match their tastes, budget, and location.

Instead of returning a raw list of venues, DineMate combines structured restaurant data with a Large Language Model (LLM). The model ranks candidate restaurants and explains why each option fits the user’s preferences, so recommendations feel personalized rather than purely filter-based.

This document captures the assignment brief and the product intent for the system to be built in this repo.

---

## Problem

Build an AI-powered restaurant recommendation service (Zomato use case). The system should intelligently suggest restaurants based on user preferences by combining structured data with an LLM.

---

## Objective

Design and implement an application that:

- Takes user preferences such as location, budget, cuisine, and ratings
- Uses a real-world dataset of restaurants
- Leverages an LLM to generate personalized, human-like recommendations
- Displays clear and useful results to the user

---

## System Workflow

### 1. Data Ingestion

- Load and preprocess the Zomato dataset from Hugging Face: [ManikaSaini/zomato-restaurant-recommendation](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation)
- Extract relevant fields such as restaurant name, location, cuisine, cost, rating, and similar attributes

### 2. User Input

Collect user preferences:

- **Location** (for example, Delhi, Bangalore)
- **Budget** (low, medium, high)
- **Cuisine** (for example, Italian, Chinese)
- **Minimum rating**
- **Additional preferences** (for example, family-friendly, quick service)

### 3. Integration Layer

- Filter and prepare relevant restaurant data based on user input
- Pass structured results into an LLM prompt
- Design a prompt that helps the LLM reason about and rank options

### 4. Recommendation Engine

Use the LLM to:

- Rank restaurants
- Provide explanations for why each recommendation fits
- Optionally summarize the set of choices

### 5. Output Display

Present top recommendations in a user-friendly format, including:

- Restaurant name
- Cuisine
- Rating
- Estimated cost
- AI-generated explanation

---

## Success Criteria

A working DineMate experience should:

1. Load real restaurant records from the specified dataset
2. Accept structured user preferences and use them to narrow candidates
3. Produce ranked recommendations with natural-language justifications
4. Show results that a diner can scan quickly (name, cuisine, rating, cost, and why it was chosen)
