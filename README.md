# Optical Network Topology Management API

This project provides a RESTful API service for managing optical network topologies, built with FastAPI and MongoDB.

## Features

-   Full CRUD operations for Networks, Topology Elements, Connections, and Services.
-   Endpoints to manage global network settings (Simulation, Spectrum Info, Span).
-   Network import and export functionalities.
-   Asynchronous from the ground up.
-   Data validation using Pydantic.

## Project Structure

The project follows a modular structure to separate concerns:

```
OptiNetSim-backend/
├── .env                  # Environment variables
├── pyproject.toml        # Project dependencies (for uv)
├── main.py               # FastAPI application entrypoint
├── README.md             # This file
└── app/
    ├── api/                # API routers and endpoints
    ├── core/               # Core configuration and DB connection
    ├── crud/               # Database interaction logic
    └── models/             # Pydantic data models
```

## Setup and Installation

### Prerequisites

-   Python 3.9+
-   `poetry` (Python package installer)
-   A running MongoDB instance

### Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/zerosignal0101/OptiNetSim-backend.git
    cd OptiNetSim-backend
    ```

2.  **Install dependencies using `uv`:**
    ```bash
    poetry install
    ```

3.  **Configure Environment Variables:**
    Create a `.env` file in the project root by copying the example:
    ```bash
    cp .env.example .env
    ```
    Modify the `.env` file with your MongoDB connection details:
    ```env
    MONGO_URI="mongodb://localhost:27017"
    MONGO_DB_NAME="optical_network_topology"
    ```

## Running the Application

To start the development server, run the following command from the project root directory:

```bash
uvicorn main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.

You can access the interactive API documentation (Swagger UI) at `http://127.0.0.1:8000/docs`.

## Database Design

The application uses a single MongoDB collection named `networks`. Each document in this collection represents an entire optical network, embedding its elements, connections, services, and global configurations. This design choice simplifies data retrieval for a complete network and ensures data consistency.

-   `network_id` corresponds to the MongoDB `_id`.
-   `element_id`, `connection_id`, and `service_id` are UUIDs generated at the application level.
