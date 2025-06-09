import scrapy
class PageItem(scrapy.Item):
    url = scrapy.Field()
    content = scrapy.Field()
    file_type = scrapy.Field()
    original_filename = scrapy.Field()