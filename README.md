# Mike V. Test Assignment

## Overview

The **text_processing** application consists of three services:
* **web_api** - The Web API interface of the application. It receives requests for text processing and returns the results. It implements two endpoints:
  * `POST /process-text`
  * `GET /results/{task_id}`
* **task_processor** - Processes incoming tasks.
* **rabbitmq** - Message broker.

This implementation does not use existing libraries like Celery, Dramatiq, Taskiq, etc. to demonstrate explicit asynchronous/synchronous text processing. Here, I/O-bound operations are performed asynchronously, while CPU-bound tasks are processed synchronously. Specifically, sending messages from `web_api` to `rabbitmq` and retrieving them by the `task_processor` service are handled asynchronously, while actual text processing occurs synchronously (in a process pool).

## System Environment

* Linux (if using the Docker bind mounts implementation in the **bind_mounts_docker_data** branch)
* Python 3.12.2
* Docker Engine 27.3.1
* Docker Compose v2.29.7

## Starting the Application

```bash
docker compose up --build
```

## Testing
**Example of a Single Request**
```bash
curl -X POST \
-u guest:guest \
-H 'Content-Type: application/json' \
-d '{"text":"Hey!/// Just wanted to confirm if we'\''re still meeting for lunch tomorrow at 12 pm.","type":"chat_item"}' \
-w '\n' \
http://127.0.0.1:8000/process-text
```

Response:
```json
{"task_id":"38dbe4df25b543699b79426dd38525db"}
```

To get the result:
```bash
curl -u guest:guest -w '\n' http://127.0.0.1:8000/results/38dbe4df25b543699b79426dd38525db | jq
```

```json
{
  "processed_text": "Hey! Just wanted to confirm if we're still meeting for lunch tomorrow at 12 pm.",
  "status": "completed",
  "created_at": "2024-11-11T13:06:32.378454",
  "word_count": 15,
  "language": "en",
  "original_text": "Hey!/// Just wanted to confirm if we're still meeting for lunch tomorrow at 12 pm.",
  "task_id": "38dbe4df-25b5-4369-9b79-426dd38525db",
  "type": "chat_item",
  "cause": null,
  "updated_at": "2024-11-11T13:06:32.732070"
}
```

## Automated Testing
Use the `test_requests_perf.py` script. Default values:
 * text size - 1MB
 * number of requests - 100

**Dependency Installation**
1. Create a virtual environment with Python 3.12.2 using your preferred method.
2. In the project root, run: `poetry install --with dev` **OR** `pip install -r requirements.txt`
3. Start the application (in the project root): `docker compose up --build`
4. In the project root, execute: `python test_requests_perf.py`

**Example**
```bash
python test_requests_perf.py
```

```
text size: 1000000
requests: 100
creating time: 2.6109304428100586
waiting time: 6.039969205856323
total time: 8.650901556015015
task completed: 100
task failed_final: 0
task unknown: 0
```

## Notes
1. Configuration for services is defined in `shared/shared/config/config.py`, including a common section: `shared_config` and separate sections for each service: `web_api_config` and `task_processor_config`. Parameters for each section can be overridden by creating corresponding `.env` files in the project root. For example, `.env.task_processor` with `CONSUMER_WORKERS_NUM=4` will set the worker process count for the `task_processor` service to 4.

2. The assignment did not specify an upper limit for `text` size in `/process-text` requests. In this implementation, it defaults to 1,000,000 characters (1MB for Latin script). It can be changed by adding `.env.web_api` in the project root with `ARTICLE_MAX_LENGTH={DESIRED_VALUE}`.

3. The language of `text` is determined with the `langdetect` library. For production, alternatives like `fastText`, `CLD3`, etc., could be considered. If a language detection error occurs, the task is marked as `failed_final` and is not retried.

4. Task statuses are as follows:
    * `pending` - in processing
    * `completed` - final status, completed successfully
    * `failed` - a temporary error (e.g., DB unavailable) occurred, and the task will be requeued
    * `failed_final` - final status, completed with an error; retrying would yield the same result

5. To manage retry logic, a specific exception `DeterministicError` is used in tasks. If this exception is raised, the message is removed from the RabbitMQ queue, avoiding a retry. In such cases, the task status is set to `failed_final`. Other exceptions result in `failed` status, prompting a retry.

6. In `web_api`, task queueing includes publisher confirmations. This behavior can be overridden in `.env.web_api`: `PRODUCER_PUBLISHER_CONFIRMS=false`.

7. By default, messages are stored persistently in the queue (RabbitMQ saves them to disk). This can be overridden in `.env.web_api`: `PRODUCER_PERSISTENT=false`.

8. Currently, texts are stored in SQLite, although storing large texts in a database is not ideal. In real conditions, it’s better to store texts (`original_text`, `processed_text`) in S3, saving only S3 object links in the database. For data transmission between services via message broker, it makes sense to store the original text in S3 at the `/process-text` endpoint stage and pass only the S3 link in the message broker.

9. Graceful shutdown implemented for `task_processor` service.

10. For `task_processor`, the default number of worker processes matches the available CPU cores (virtual) of the container. This can be overridden in `.env.task_processor`: `CONSUMER_WORKERS_NUM={DESIRED_VALUE}`.

11. For `task_processor`, `prefetch_count` (to prevent worker idle time when fetching messages) defaults to twice the `consumer_workers_num`. This can be overridden in `.env.task_processor`: `CONSUMER_PREFETCH_COUNT={DESIRED_VALUE}`.

12. Task results are stored in SQLite DB with a Docker volume created for this purpose. For direct access, the database can be stored on the host (`./docker_data` in the project root) and mounted into containers. This is available in the `bind_mounts_docker_data` branch (Linux only).

13. If `task_id` is generated on the client side and passed to `/process-text`, requests become idempotent.

14. Potential features that could be implemented(**not implemented** in current project):
    * "requeue with delay" - delayed retry for tasks
    * Service monitoring (Prometheus/Grafana)
    * Centralized log storage and access (e.g., ELK stack)
    * Unit tests

15. The `task_processor` service can scale to any number of instances, as can `web_api` and `rabbitmq`.

16. Multi-stage builds optimize Docker image creation.

17. To ensure reproducible builds, dependencies are installed from `poetry.lock` during image builds.

# Test assignment requirements
**Test Task for Senior Python Developer Position**

**Task Overview:**
Create a microservice that:

1. **FastAPI Endpoint:**
    * Exposes a POST endpoint at `/process-text`.
    * Accepts a JSON payload containing the following field:
        * `text`: A string of text data to be processed.
        * `type`: Either `chat_item`, `summary` or `article`.

        *Expect `chat_item` to be up to 300 symbols, `summary` up to 3000 symbols; `article` assumes a large text size - more than 300000 symbols.*

2. **Message Queue Integration:**

   Upon receiving a request, the service should:

    * Validate the input data.
    * Generate a unique `task_id` (UUID).
    * Publish a message to a message queue (RabbitMQ or Kafka) containing:
        * `task_id`
        * `text`
        * `type`

3. **Background Worker:**

    * A separate consumer service listens to the message queue.
    * When a message is received, it performs the following text processing tasks:
    * **Word Count:** Count the number of words in the original text.
    * **Language Detection:** Detect the language of the original text.
    * **Text Cleaning:** Remove all symbols from the text except for the following:
        `- : ( ) , . ! ? “ ” '`

    * Stores the results in a local SQLite database or flat file with the following schema:

        * `task_id`: UUID
        * `original_text`: The original text received
        * `processed_text`: The text after cleaning
        * `type`: Text type received
        * `word_count`: Integer
        * `language`: Detected language code (e.g., ‘en’ for English)
        * `status`: Processing status (e.g., “completed”)

4. **Result Retrieval Endpoint:**

    * Exposes a **GET** endpoint at `/results/{task_id}`.
    * Returns a JSON response containing:
        * `task_id`
        * `original_text`
        * `processed_text`
        * `word_count`
        * `language`
        * `status`

**Requirements:**

* Use **FastAPI** for building the web service.
* Use **RabbitMQ** or **Kafka** for the message queue system.
* Containerize the application using **Docker** and orchestrate services with **docker-compose**.
* Ensure the application is executable in a local Docker environment.
* ***Ensure the architecture is optimized for heavy loads, up to 100 messages per minute.***
* Write clean, maintainable, and well-documented code.
* Include proper error handling and input validation.
* Provide a **README** with setup and execution instructions.
* Provide a **requirements.txt** and **.env** if needed.
* Use any pip library as required as long as the microservice is executable in the local environment.

**Optional Enhancements (if time permits):**

* **Implement asynchronous processing with asyncio. Strong plus.**
* Add unit tests for key components using a testing framework like pytest.
* Include logging for monitoring and debugging purposes.
* Secure the endpoints with basic authentication.

**Deliverables:**

* Source code of the application.
* Dockerfile and docker-compose.yml files for containerization.
* A **README** file containing:
    * Project description.
    * Setup instructions.
    * How to run the application.
    * Examples of API requests and responses
* requirements.txt
* .env

**Time Estimate:**

* The task is designed to be completed in **3 to 4 hours**.

**Submission Guidelines:**

* Submit your solution as a link to a public Git repository (e.g., GitHub, GitLab).
* Ensure that all dependencies and setup steps are clearly defined.
* Include any assumptions or decisions you made during development.

**Evaluation Criteria:**

* **Functionality:** The application meets all the specified requirements.
* **Code Quality:** Code is clean, well-organized, and follows best practices.
* **Documentation:** Clear instructions and documentation are provided.
* **Optional Enhancements:** If included.

**Data Example:**

**Input:**

```json
{
  "type": "chat_item",
  "content": "Hey!/// Just wanted to confirm if we're still meeting for lunch tomorrow at 12 pm."
}
```

**Output:**

```json
{
  "task_id": "b6a7f1a2-3c4d-5e6f-7890-1a2b3c4d5e6f",
  "original_text": "Hey!/// Just wanted to confirm if we're still meeting for lunch tomorrow at 12 pm.",
  "processed_text": "Hey! Just wanted to confirm if we're still meeting for lunch tomorrow at 12 pm.",
  "type": "chat_item",
  "word_count": 15,
  "language": "en",
  "status": "completed"
}
```
