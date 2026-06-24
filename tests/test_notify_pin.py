import unittest

from app.notify_pin import hash_notify_pin, verify_notify_pin_for_recipient


class NotifyPinTests(unittest.TestCase):
    def test_plaintext_fallback_when_hash_mobile_mismatch(self):
        store_id = 8
        pin = "1234"
        old_mobile = "6900000000"
        new_mobile = "6911111111"
        stale_hash = hash_notify_pin(store_id=store_id, mobile=old_mobile, pin=pin)
        ok = verify_notify_pin_for_recipient(
            store_id=store_id,
            mobile=new_mobile,
            pin=pin,
            pin_hash=stale_hash,
            pin_plain=pin,
        )
        self.assertTrue(ok)

    def test_hash_match_with_normalized_mobile(self):
        store_id = 3
        pin = "5678"
        mobile = "6901234567"
        pin_hash = hash_notify_pin(store_id=store_id, mobile=mobile, pin=pin)
        ok = verify_notify_pin_for_recipient(
            store_id=store_id,
            mobile="30" + mobile,
            pin=pin,
            pin_hash=pin_hash,
            pin_plain=None,
        )
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
