import base64

from pyasn1.codec.der import encoder
import rfc3161ng


class TimeSigner:
    def __init__(self, ts_url, ts_certfile):
        self.ts_url = ts_url
        self.ts_certfile = ts_certfile

        with open(self.ts_certfile, "rb") as fh_in:
            self.cert_pem = fh_in.read()

        self.time_stamper = rfc3161ng.RemoteTimestamper(
            self.ts_url, certificate=self.cert_pem, hashname="sha256"
        )

    def sign(self, text):
        tsr = self.time_stamper(data=text.encode("ascii"), return_tsr=True)

        result = encoder.encode(tsr)

        return base64.b64encode(result)

    def verify(self, text, timeSignature, created, delta):
        resp = rfc3161ng.decode_timestamp_response(base64.b64decode(timeSignature))
        tst = resp.time_stamp_token

        # verify timestamp was signed by the existing cert
        try:
            if not rfc3161ng.check_timestamp(
                tst,
                certificate=self.cert_pem,
                data=text.encode("ascii"),
                hashname="sha256",
            ):
                return False
        except Exception as e:
            return False

        # check signature occured within specified delta of creation date
        timestamp = rfc3161ng.get_timestamp(tst)

        return timestamp - created < delta and timestamp >= created