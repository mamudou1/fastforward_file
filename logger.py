import logging  # Import the standard Python logging module

class Logger:
    def __init__(self, name='sync_logger', log_level='INFO', log_file='sync.log'):
        # Create or retrieve a logger instance with the given name
        self.logger = logging.getLogger(name)

        # Set the logging level (e.g., DEBUG, INFO, WARNING) based on config
        self.logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

        # Prevent duplicate handlers if logger is initialized multiple times
        if not self.logger.handlers:
            # Create a file handler to write logs to a file
            handler = logging.FileHandler(log_file, encoding='utf-8')

            # Define the log message format: timestamp - log level - message
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)

            # Add the handler to the logger
            self.logger.addHandler(handler)

    def get_logger(self):
        # Return the configured logger instance
        return self.logger
