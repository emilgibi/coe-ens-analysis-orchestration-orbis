import logging
import sys
import contextvars

session_id_var = contextvars.ContextVar("session_id", default="")
ens_id_var = contextvars.ContextVar("ens_id", default="")

logging.getLogger().handlers.clear()
# Create a logger
logger = logging.getLogger("console_logger")
logger.setLevel(logging.INFO)  # Set the lowest log level to capture all messages
# logger.handlers.clear()
logger.propagate = False
# Create a console handler (prints logs to console)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)  # Set handler level to show all logs

# Define log message format
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(session_id)s - %(ens_id)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
console_handler.setFormatter(formatter)  # Apply the custom formatting to the handler


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.session_id = session_id_var.get()
        record.ens_id = ens_id_var.get()
        return True


logger.addFilter(RequestIdFilter())

# Add console handler to logger (avoid adding multiple handlers)
if not logger.hasHandlers():
    logger.addHandler(console_handler)
