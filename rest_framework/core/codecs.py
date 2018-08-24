
class BaseParser(object):
    media_type = None

    def parse(self, stream, media_type=None, parser_context=None):
        raise NotImplementedError(".parse() must be overridden.")


class JSONParser(BaseParser):
    media_type = 'application/json'

    async def parse(self, request):
        data = await request.json()
        return data


PARSER_MEDIA_TYPE = (JSONParser(),)
