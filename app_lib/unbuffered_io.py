class UnbufferedIO(object):
    """ Class to unbuffer IO """
    def __init__(self, stream):
        self.stream = stream

    def write(self, data):
        """ function to write bufferdata """
        self.stream.write(data)
        self.stream.flush()

    def writelines(self, datas):
        """ function to bufferdata writelines """
        self.stream.writelines(datas)
        self.stream.flush()

    def __getattr__(self, attr):
        return getattr(self.stream, attr)
