from capwin import *
def test_pyapp():
    services = OrderedDict([
        ('ultra', Ultra()),
        ('click', Click()),
        ('sbi', Sbi()),
        ('raku', Raku()),
        ('lion', Lion()),
        ('gaitame', Gaitame()),
        ('try', Try()),
        ('nano', Nano()),
    ])
    service = services['ultra']
    #service.make_train_data(interactive=False)
    service.train()
    #service.new_recognizer.modify_train_data()
    service.load_file()
    pprint(service.recognize())
