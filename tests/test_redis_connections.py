import socket

from sqldesk import _redis, redis_connection, rq_redis_connection, settings
from tests import BaseTestCase


class TestTheRedisClientsNoticeADeadPeer(BaseTestCase):
    """
    A connection whose other end has gone away -- a laptop that slept, a
    network blip -- leaves the next command blocked in recv() until the kernel
    gives up on the TCP connection, which is about fifteen minutes. For the
    scheduler that is fifteen minutes of scheduling nothing while the process
    looks perfectly healthy. Measured on the development cluster: twenty-four
    minutes of exactly that.

    So the clients are built with a health check and keepalive, and this says
    so, because `redis.from_url(url)` is the obvious thing to write and it has
    neither.

    Built through the factory rather than read off the module-level clients:
    an RQ Worker raises the socket timeout on whatever connection it is given,
    on purpose, so those two carry whatever the last worker in this process
    decided.
    """

    def setUp(self):
        super().setUp()
        self.kwargs = _redis(settings.REDIS_URL).connection_pool.connection_kwargs

    def test_an_idle_connection_is_checked_before_it_is_used_again(self):
        self.assertGreater(self.kwargs.get("health_check_interval", 0), 0)

    def test_the_kernel_is_asked_to_notice_a_dead_peer(self):
        self.assertTrue(self.kwargs.get("socket_keepalive"))

        options = self.kwargs.get("socket_keepalive_options") or {}
        # Linux's names. A platform without them gets plain keepalive, which
        # is still better than none, so this only checks where they exist.
        if hasattr(socket, "TCP_KEEPIDLE"):
            self.assertIn(socket.TCP_KEEPIDLE, options)
            self.assertLessEqual(options[socket.TCP_KEEPIDLE], 120)

    def test_we_set_no_socket_timeout_of_our_own(self):
        # An RQ worker waits on BLPOP for longer than any sensible socket
        # timeout, and sets one to suit itself when it starts. One chosen here
        # would either be ignored or turn an idle worker into a reconnect
        # loop, which is worse than the problem being solved.
        self.assertIsNone(self.kwargs.get("socket_timeout"))

    def test_and_the_real_connections_talk_to_redis(self):
        for connection in (redis_connection, rq_redis_connection):
            self.assertTrue(connection.ping())
