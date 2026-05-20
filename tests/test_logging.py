from quantuum.logging_setup import bind_request_id, configure_logging, get_logger


def test_logging_configures_and_binds():
    configure_logging()
    bind_request_id("abc-123")
    logger = get_logger("test")
    # Should not raise; structlog returns a bound logger.
    logger.info("hello", foo="bar")
