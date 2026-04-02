"""
Tests for Block 3: Output Channel abstraction and CLI implementation.
All tests follow T3.1–T3.6 from the design plan.
"""

import io

import pytest

from tbc_agent.output_channels import (
    DeliveryOutcome,
    ResponseRecord,
    CliChannel,
)


# ---------------------------------------------------------------------------
# T3.1 – T3.2: Contract
# ---------------------------------------------------------------------------

class TestOutputChannelContract:
    def test_T3_1_returns_delivery_outcome(self):
        """T3.1: deliver() returns a DeliveryOutcome."""
        channel = CliChannel(stream=io.StringIO())
        record = ResponseRecord(reply_text="hello")
        result = channel.deliver(record)

        assert isinstance(result, DeliveryOutcome)

    def test_T3_2_response_record_not_mutated(self):
        """T3.2: The response record is unchanged after delivery."""
        channel = CliChannel(stream=io.StringIO())
        record = ResponseRecord(reply_text="original text")
        original_text = record.reply_text

        channel.deliver(record)

        assert record.reply_text == original_text


# ---------------------------------------------------------------------------
# T3.3 – T3.6: CLI implementation
# ---------------------------------------------------------------------------

class TestCliChannel:
    def test_T3_3_reply_text_printed_to_stream(self):
        """T3.3: The reply text is written to the output stream."""
        out = io.StringIO()
        channel = CliChannel(stream=out)
        channel.deliver(ResponseRecord(reply_text="the answer"))

        assert "the answer" in out.getvalue()

    def test_T3_4_successful_print_returns_success(self):
        """T3.4: A successful delivery returns a success outcome."""
        channel = CliChannel(stream=io.StringIO())
        result = channel.deliver(ResponseRecord(reply_text="hi"))

        assert result.success is True

    def test_T3_5_error_message_delivered_same_as_normal_response(self):
        """T3.5: An error message string is delivered identically to a normal response."""
        out = io.StringIO()
        channel = CliChannel(stream=out)
        result = channel.deliver(ResponseRecord(reply_text="I was unable to get a response, please try again"))

        assert result.success is True
        assert "unable to get a response" in out.getvalue()

    def test_T3_6_empty_reply_text_handled_gracefully(self):
        """T3.6: Empty reply text does not raise an error and returns success."""
        out = io.StringIO()
        channel = CliChannel(stream=out)
        result = channel.deliver(ResponseRecord(reply_text=""))

        assert result.success is True
