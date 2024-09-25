# handler_wrapper.py

import time
import threading

class HandlerWrapper:
    def __init__(self, handler_class, init_args=None, init_kwargs=None, retry_interval=300):
        self.handler_class = handler_class
        self.init_args = init_args if init_args is not None else ()
        self.init_kwargs = init_kwargs if init_kwargs is not None else {}
        self.retry_interval = retry_interval  # in seconds
        self.handler = None
        self.initialized = False
        self.last_exception = None
        self._stop_reinit_thread = threading.Event()

        self.attempt_initialization()

        # Start the background thread for periodic re-initialization
        self.start_periodic_reinitialization()

    def attempt_initialization(self):
        try:
            self.handler = self.handler_class(*self.init_args, **self.init_kwargs)
            self.initialized = True
            self.last_exception = None
            print(f"{self.handler_class.__name__} initialized successfully.")
        except Exception as e:
            self.handler = None
            self.initialized = False
            self.last_exception = e
            print(f"Warning: Failed to initialize {self.handler_class.__name__}. Exception: {e}")

    def is_initialized(self):
        return self.initialized

    def update_db(self, info):
        if not self.initialized:
            print(f"{self.handler_class.__name__} is not initialized. Skipping update.")
            return f"{self.handler_class.__name__} update skipped due to initialization failure."
        try:
            return self.handler.update_db(info)
        except Exception as e:
            print(f"Warning: Failed to update database {self.handler_class.__name__}. Exception: {e}")
            # Optionally, reset initialized flag to retry initialization
            self.initialized = False
            self.last_exception = e
            return f"Failed to update {self.handler_class.__name__} due to an error."

    def start_periodic_reinitialization(self):
        def reinit_loop():
            while not self._stop_reinit_thread.is_set():
                if not self.initialized:
                    print(f"Attempting to re-initialize {self.handler_class.__name__}...")
                    self.attempt_initialization()
                # Sleep for the retry interval or until the event is set
                self._stop_reinit_thread.wait(self.retry_interval)
        self._reinit_thread = threading.Thread(target=reinit_loop, daemon=True)
        self._reinit_thread.start()

    def stop_periodic_reinitialization(self):
        self._stop_reinit_thread.set()
        self._reinit_thread.join()
