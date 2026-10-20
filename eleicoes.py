"""
Eleições disponíveis no seletor — o 2º turno de cada eleição presidencial
brasileira realizada com urna eletrônica.

Por que só 2º turno: num segundo turno a cédula tem um único cargo
(Presidente) e exatamente dois candidatos, e toda urna do país roda a mesma
eleição. É o cenário mais simples de simular e o que melhor mostra a tela de
confirmação do voto.

Por que estes anos: a urna eletrônica cobriu 57,62% do eleitorado em 1998 —
ano em que, além disso, não houve 2º turno presidencial. A primeira eleição
100% eletrônica foi a municipal de 2000. Logo, os 2ºs turnos presidenciais
realizados integralmente em urna eletrônica são 2002, 2006, 2010, 2014, 2018
e 2022; 2026 entra como o turno hipotético deste estudo.

Os anos são reais; os candidatos, partidos e números são todos fictícios —
este é um estudo de interface, não um registro histórico.
"""

# Seção única, usada por todos os anos: no 2º turno cada urna do país roda a
# mesma cédula de cargo único, então a seção é só texto de ambiente e não
# precisa variar por eleição.
SECAO = {'zona': '014', 'secao': '0412', 'local': 'São Paulo · SP'}

ELEICOES = {
    '2026': {
        'ano': '2026',
        'rotulo': '2026 · 2º turno',
        'kicker': 'Estudo de interface · 2º turno hipotético de 2026 · candidatos fictícios',
        'cands': [
            {'num': '37', 'nome': 'Helena Duarte Ramos', 'partido': 'PRV',
             'vice': 'Otávio Lins Barreto', 'gender': 'f', 'gender_vice': 'm'},
            {'num': '48', 'nome': 'Marcos Tavares Albuquerque', 'partido': 'MNB',
             'vice': 'Cecília Prado', 'gender': 'm', 'gender_vice': 'f'},
        ],
    },
    '2022': {
        'ano': '2022',
        'rotulo': '2022 · 2º turno',
        'kicker': 'Estudo de interface · 2º turno de 2022 · candidatos fictícios',
        'cands': [
            {'num': '61', 'nome': 'Joana Sato Ferreira', 'partido': 'PDA',
             'vice': 'Ricardo Menezes', 'gender': 'f', 'gender_vice': 'm'},
            {'num': '84', 'nome': 'Paulo Henrique Costa', 'partido': 'UCT',
             'vice': 'Lúcia Andrade', 'gender': 'm', 'gender_vice': 'f'},
        ],
    },
    '2018': {
        'ano': '2018',
        'rotulo': '2018 · 2º turno',
        'kicker': 'Estudo de interface · 2º turno de 2018 · candidatos fictícios',
        'cands': [
            {'num': '23', 'nome': 'Beatriz Nogueira Alves', 'partido': 'FPL',
             'vice': 'Henrique Salles', 'gender': 'f', 'gender_vice': 'm'},
            {'num': '55', 'nome': 'Gustavo Rezende Pinho', 'partido': 'ARN',
             'vice': 'Teresa Bittencourt', 'gender': 'm', 'gender_vice': 'f'},
        ],
    },
    '2014': {
        'ano': '2014',
        'rotulo': '2014 · 2º turno',
        'kicker': 'Estudo de interface · 2º turno de 2014 · candidatos fictícios',
        'cands': [
            {'num': '19', 'nome': 'Clarice Monteiro Vaz', 'partido': 'PNU',
             'vice': 'Álvaro Siqueira', 'gender': 'f', 'gender_vice': 'm'},
            {'num': '72', 'nome': 'Eduardo Brandão Mesquita', 'partido': 'MDL',
             'vice': 'Sônia Vilalba', 'gender': 'm', 'gender_vice': 'f'},
        ],
    },
    '2010': {
        'ano': '2010',
        'rotulo': '2010 · 2º turno',
        'kicker': 'Estudo de interface · 2º turno de 2010 · candidatos fictícios',
        'cands': [
            {'num': '31', 'nome': 'Rosana Teixeira Goulart', 'partido': 'PCV',
             'vice': 'Ismael Fontoura', 'gender': 'f', 'gender_vice': 'm'},
            {'num': '66', 'nome': 'Vicente Aragão Peixoto', 'partido': 'UNR',
             'vice': 'Marta Queiroga', 'gender': 'm', 'gender_vice': 'f'},
        ],
    },
    '2006': {
        'ano': '2006',
        'rotulo': '2006 · 2º turno',
        'kicker': 'Estudo de interface · 2º turno de 2006 · candidatos fictícios',
        'cands': [
            {'num': '27', 'nome': 'Jorge Amâncio Vieira', 'partido': 'PTF',
             'vice': 'Regina Caldeira', 'gender': 'm', 'gender_vice': 'f'},
            {'num': '93', 'nome': 'Silvana Boaventura Reis', 'partido': 'DRN',
             'vice': 'Adriano Quental', 'gender': 'f', 'gender_vice': 'm'},
        ],
    },
    '2002': {
        'ano': '2002',
        'rotulo': '2002 · 2º turno',
        'kicker': 'Estudo de interface · 2º turno de 2002 · candidatos fictícios',
        'cands': [
            {'num': '14', 'nome': 'Nelson Figueiró Lacerda', 'partido': 'PBI',
             'vice': 'Yara Cavalcanti', 'gender': 'm', 'gender_vice': 'f'},
            {'num': '58', 'nome': 'Amélia Ventura Drummond', 'partido': 'RSD',
             'vice': 'Caio Belmonte', 'gender': 'f', 'gender_vice': 'm'},
        ],
    },
}

# Mais recente primeiro — a ordem em que o seletor lista as eleições.
ORDEM = ['2026', '2022', '2018', '2014', '2010', '2006', '2002']

DEFAULT = '2026'


def get(ano):
    """A eleição pedida, caindo no padrão se o ano não existir."""
    return ELEICOES.get(str(ano), ELEICOES[DEFAULT])


def cands_map(ano):
    """{número: candidato} — o formato de busca por 2 dígitos da urna."""
    return {c['num']: c for c in get(ano)['cands']}


def numeros(ano):
    """Os dois números válidos do ano, para a dica de teste da página."""
    return [c['num'] for c in get(ano)['cands']]


def secao_label():
    """'Seção 0412 · Zona 014' — como aparece nos recibos e na tela."""
    return f'Seção {SECAO["secao"]} · Zona {SECAO["zona"]}'
