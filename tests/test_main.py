import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import main


class ArquivosTemporarios(unittest.TestCase):
    def setUp(self):
        self.diretorio = tempfile.TemporaryDirectory()
        self.anterior = os.getcwd()
        os.chdir(self.diretorio.name)
        main.inicializar_arquivos()

    def tearDown(self):
        os.chdir(self.anterior)
        self.diretorio.cleanup()


class ArquivosTest(ArquivosTemporarios):
    def test_busca_nao_muda_resultado_da_conferencia_por_valor(self):
        main.salvar_linhas('a1.txt', ['Primeiro 25,00 D', 'Segundo 25,00 D'])
        main.salvar_linhas('a2.txt', ['Externo 25,00 D'])
        resultado, total, faltando = main.calcular_lancamentos(termo='Segundo')
        self.assertEqual(resultado, [(2, 'Segundo 25,00 D', False)])
        self.assertEqual((total, faltando), (1, 1))

    def test_credito_nao_confere_debito_do_mesmo_valor(self):
        main.salvar_linhas('a1.txt', ['Saída 100,00 D', 'Entrada 100,00 C',
                                    'Outra entrada 100,00 C', 'Sem marcador 100,00'])
        main.salvar_linhas('a2.txt', ['Entrada externa 100,00 C'])
        resultado, total, faltando = main.calcular_lancamentos()
        self.assertEqual((total, faltando), (3, 2))
        self.assertEqual([ok for _, _, ok in resultado], [False, True, False])
        self.assertEqual(main.calcular_lancamentos('C')[1:], (2, 1))
        self.assertEqual(main.calcular_lancamentos('D')[1:], (1, 1))
        main.salvar_linhas('a2.txt', ['Saída externa 100,00 D'])
        self.assertEqual([ok for _, _, ok in main.calcular_lancamentos()[0]],
                         [True, False, False])

    def test_relatorio_inclui_creditos_e_respeita_filtro(self):
        main.salvar_linhas('a1.txt', ['Saída 50,00 D', 'Entrada 50,00 C'])
        main.salvar_linhas('a2.txt', ['[2] Entrada 50,00 C'])
        with patch.object(main.webbrowser, 'open'):
            caminho = main.gerar_relatorio_html()
            html = Path(caminho).read_text(encoding='utf-8')
            self.assertIn('Saída 50,00 D', html)
            self.assertIn('Entrada 50,00 C', html)
            self.assertIn('<td>Crédito</td>', html)
            self.assertIn('<b>Faltando no A2:</b> 1', html)
            main.gerar_relatorio_html('C')
        html = Path(caminho).read_text(encoding='utf-8')
        self.assertIn('Entrada 50,00 C', html)
        self.assertNotIn('Saída 50,00 D', html)
        self.assertIn('<b>Faltando no A2:</b> 0', html)

    def test_relatorio_preserva_ordem_original_mesmo_com_datas_no_texto(self):
        main.salvar_linhas('a1.txt', ['30/10/2026 Último 30,00 D',
                                    '01/10/2026 Primeiro 10,00 D'])
        with patch.object(main.webbrowser, 'open'):
            caminho = main.gerar_relatorio_html()
        html = Path(caminho).read_text(encoding='utf-8')
        self.assertLess(html.index('Último'), html.index('Primeiro'))
        self.assertEqual([n for n, _, _ in main.calcular_debitos()[0]], [1, 2])

    def test_valores_brasileiros_equivalentes(self):
        self.assertEqual(main.extrair_valor_debito('Cliente 1.453,30 D'),
                         main.extrair_valor_debito('Cliente 1453,3 D'))
        self.assertEqual(main.extrair_valor_debito('Cliente 0,00 d'), 0)
        for texto in ('Cliente 12,00 C', 'Cliente 1,234 D',
                      'Cliente 12.34 D', 'Cliente -12,00 D'):
            with self.subTest(texto=texto):
                self.assertIsNone(main.extrair_valor_debito(texto))

    def test_formato_do_arquivo_historico_com_valor_colado(self):
        from decimal import Decimal
        self.assertEqual(main.extrair_valor_debito('118542ENVIO TED320,00 D'), Decimal('320.00'))
        self.assertEqual(main.extrair_valor_debito('132784ENVIO TED1.125,90 D'), Decimal('1125.90'))
        self.assertIsNone(main.extrair_valor_debito('756CRED TED2.350,00 C'))

    def test_cada_ocorrencia_do_a2_confere_apenas_um_debito(self):
        main.salvar_linhas('a1.txt', ['A 1.453,30 D', '', 'B 1453,30 D', 'C 10,00 C'])
        main.salvar_linhas('a2.txt', ['[1] A 1453,3 D'])
        resultado, total, faltando = main.calcular_debitos()
        self.assertEqual((total, faltando), (2, 1))
        self.assertEqual([(n, ok) for n, _, ok in resultado], [(1, True), (3, False)])
        main.salvar_linhas('a2.txt', ['[1] A 1453,3 D', '[3] B 1.453,30 D'])
        self.assertEqual(main.calcular_debitos()[1:], (2, 0))

    def test_relatorio_preserva_texto_sem_interpretar_html(self):
        main.salvar_linhas('a1.txt', ['<script>alert(1)</script> & Cliente 12,00 D'])
        with patch.object(main.webbrowser, 'open') as abrir:
            caminho = main.gerar_relatorio_html()
        html = Path(caminho).read_text(encoding='utf-8')
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt; &amp; Cliente', html)
        self.assertNotIn('<script>', html)
        self.assertIn('FALTA NO A2', html)
        abrir.assert_called_once_with(Path(caminho).resolve().as_uri())

    def test_falha_na_substituicao_preserva_arquivo_e_remove_temporario(self):
        main.salvar_linhas('a2.txt', ['original'])
        antes = set(Path('.').iterdir())
        with patch.object(main.os, 'replace', side_effect=OSError('Disco indisponível')):
            with self.assertRaises(OSError):
                main.salvar_linhas('a2.txt', ['novo'])
        self.assertEqual(main.carregar_linhas('a2.txt'), ['original'])
        self.assertEqual(set(Path('.').iterdir()), antes)

    def test_configuracao_invalida_usa_padrao(self):
        for conteudo in ('null', '[]', '123', '{', '{"acento": [], "tema": {}}'):
            with self.subTest(conteudo=conteudo):
                Path(main.CONFIG).write_text(conteudo, encoding='utf-8')
                self.assertEqual(main.carregar_config(), ('Escuro', 'Azul'))

    def test_selecao_da_segunda_linha_nao_confere_primeira_de_mesmo_valor(self):
        main.salvar_linhas('a1.txt', ['Primeiro 25,00 D', 'Segundo 25,00 D'])
        main.salvar_linhas('a2.txt', ['[2] Segundo 25,00 D'])
        resultado, total, faltando = main.calcular_debitos()
        self.assertEqual([ok for _, _, ok in resultado], [False, True])
        self.assertEqual((total, faltando), (2, 1))


@unittest.skipUnless(os.environ.get('DISPLAY'), 'Requer uma tela X11')
class InterfaceTest(ArquivosTemporarios):
    def setUp(self):
        super().setUp()
        self.app = main.App()
        self.app.update()

    def tearDown(self):
        for evento in self.app.tk.call('after', 'info'):
            self.app.tk.call('after', 'cancel', evento)
        self.app.destroy()
        super().tearDown()

    def test_busca_adicao_exportacao_e_remocao_atualizam_debitos(self):
        main.salvar_linhas('a1.txt', ['Cliente 1.453,30 D', 'Outro 25,00 D'])
        self.app.busca_var.set('145330')
        self.app.buscar_a1()
        self.assertEqual(len(self.app.tree_busca.get_children()), 1)
        self.app.tree_busca.selection_set('0')
        self.app.adicionar_selecionados()
        self.assertEqual(self.app.var_falta.get(), '0')
        self.app.exportar()
        self.assertEqual(main.carregar_linhas('No/N.txt'), ['[1] Cliente 1.453,30 D'])
        self.app.tree_a2.selection_set('0')
        with patch.object(main.messagebox, 'askyesno', return_value=True):
            self.app.remover_a2()
        self.assertEqual(main.carregar_linhas('a2.txt'), [])
        self.assertEqual(self.app.var_falta.get(), '1')

    def test_duplicatas_podem_ser_exibidas_e_removidas_individualmente(self):
        item = '[1] Cliente 12,00 D'
        main.salvar_linhas('a2.txt', [item, item, '[2] Outro 25,00 D'])
        self.app.filtro_a2.set('Cliente')
        self.app.atualizar_a2()
        self.assertEqual(len(self.app.tree_a2.get_children()), 2)
        self.app.tree_a2.selection_set('1')
        with patch.object(main.messagebox, 'askyesno', return_value=True):
            self.app.remover_a2()
        self.assertEqual(main.carregar_linhas('a2.txt'), [item, '[2] Outro 25,00 D'])

    def test_remocao_nao_sobrescreve_alteracao_externa(self):
        main.salvar_linhas('a2.txt', ['[1] Cliente 12,00 D'])
        self.app.atualizar_a2()
        self.app.tree_a2.selection_set('0')
        main.salvar_linhas('a2.txt', ['[2] Outro 25,00 D'])
        with patch.object(main.messagebox, 'askyesno', return_value=True):
            self.app.remover_a2()
        self.assertEqual(main.carregar_linhas('a2.txt'), ['[2] Outro 25,00 D'])
        self.assertIn('foi alterado', self.app.status.get())

    def test_numeracao_crescente_ate_fim_em_todas_as_abas(self):
        # Mais de 30 entradas, linhas vazias e A2 fora de ordem.
        main.salvar_linhas('a1.txt', ['', 'Crédito 10,00 C'] +
                          [f'Cliente {i},00 D' for i in range(1, 36)])
        main.salvar_linhas('a2.txt', ['[35] Cliente 33,00 D', '[3] Cliente 1,00 D',
                                    '[12] Cliente 10,00 D'])
        self.app.atualizar_tudo()
        for tree, quantidade in ((self.app.tree_busca, 36), (self.app.tree_a2, 3),
                                 (self.app.tree_deb, 36)):
            numeros = [int(tree.set(iid, 'ordem')) for iid in tree.get_children()]
            self.assertEqual(numeros, list(range(1, quantidade + 1)))
            originais = [int(tree.set(iid, 'linha')) for iid in tree.get_children()]
            self.assertEqual(originais, sorted(originais))
        self.assertEqual(self.app.tree_deb.set('0', 'linha'), '2')
        self.app.filtro_a2.set('33,00')
        iid, = self.app.tree_a2.get_children()
        self.assertEqual(self.app.tree_a2.set(iid, 'ordem'), '1')
        self.assertEqual(self.app.tree_a2.set(iid, 'linha'), '35')
        self.app.busca_var.set('35,00'); self.app.buscar_a1()
        self.assertEqual(self.app.tree_busca.set('0', 'ordem'), '1')
        self.assertEqual(self.app.tree_busca.set('0', 'linha'), '37')
        self.app.mostrar_todos()
        self.assertEqual(len(self.app.tree_busca.get_children()), 36)

    def test_adicionar_e_comparar_destaca_selecao_e_preserva_origem(self):
        main.salvar_linhas('a1.txt', ['Primeiro 25,00 D', '', 'Segundo 25,00 D',
                                    'Crédito 10,00 C'])
        self.app.mostrar_todos()
        self.app.tree_busca.selection_set('1', '2')
        self.app.adicionar_e_comparar()
        self.assertEqual(self.app.abas.get(), 'Buscar e comparar')
        self.assertEqual(self.app.tree_deb.selection(), ('1', '2'))
        self.assertEqual(self.app.tree_deb.set('1', 'linha'), '3')
        self.assertEqual(self.app.tree_deb.set('1', 'situacao'), 'OK')
        self.assertEqual(self.app.tree_deb.set('0', 'situacao'), 'FALTA NO A2')
        self.assertEqual(main.carregar_linhas('a2.txt'),
                         ['[3] Segundo 25,00 D', '[4] Crédito 10,00 C'])

    def test_comparar_sem_selecao_nao_muda_aba_nem_arquivo(self):
        self.app.adicionar_e_comparar()
        self.assertEqual(self.app.abas.get(), 'Buscar e comparar')
        self.assertEqual(main.carregar_linhas('a2.txt'), [])

    def test_ordem_das_linhas_nas_tres_abas_sem_inferir_datas(self):
        registros = ['Sem data 99,00 D', '30/10/2026 Último 30,00 D',
                     '02/10/2026 Segundo 20,00 D', '01/10/2026 Primeiro 10,00 D']
        main.salvar_linhas('a1.txt', registros)
        main.salvar_linhas('a2.txt', [f'[{n}] {t}' for n, t in enumerate(registros, 1)])
        self.app.atualizar_tudo()
        for tree in (self.app.tree_busca, self.app.tree_a2, self.app.tree_deb):
            self.assertEqual([tree.set(i, 'linha') for i in tree.get_children()],
                             ['1', '2', '3', '4'])
            self.assertEqual([tree.set(i, 'ordem') for i in tree.get_children()],
                             ['1', '2', '3', '4'])
        self.app.exportar()
        self.assertEqual(main.carregar_linhas('No/N.txt'), main.obter_destino_ordenado())
        self.assertIn('Sem data', main.carregar_linhas('No/N.txt')[0])

    def test_filtros_debito_credito_e_relatorio(self):
        main.salvar_linhas('a1.txt', ['Saída 25,00 D', 'Entrada 25,00 C',
                                    'Outra entrada 30,00 C'])
        main.salvar_linhas('a2.txt', ['[2] Entrada 25,00 C'])
        self.app.atualizar_tudo()
        self.assertEqual((self.app.var_total.get(), self.app.var_falta.get()), ('3', '2'))
        self.app.tipo_comparacao.set('Créditos')
        self.assertEqual((self.app.var_total.get(), self.app.var_falta.get()), ('2', '1'))
        self.assertEqual([self.app.tree_deb.set(i, 'tipo') for i in self.app.tree_deb.get_children()],
                         ['Crédito', 'Crédito'])
        with patch.object(main.webbrowser, 'open'):
            self.app.imprimir_relatorio()
        html = Path('No/relatorio_debitos.html').read_text(encoding='utf-8')
        self.assertIn('Entrada 25,00 C', html)
        self.assertNotIn('Saída 25,00 D', html)
        self.app.tipo_comparacao.set('Débitos')
        self.assertEqual((self.app.var_total.get(), self.app.var_falta.get()), ('1', '1'))
        self.app.mostrar_todos()
        self.app.tree_busca.selection_set('1')
        self.app.adicionar_e_comparar()
        self.assertEqual(self.app.tipo_comparacao.get(), 'Todos')
        self.assertEqual(self.app.tree_deb.selection(), ('1',))
        self.assertEqual(self.app.tree_deb.set('1', 'tipo'), 'Crédito')

    def test_busca_conjunta_e_inclusao_atualizam_sem_trocar_aba(self):
        main.salvar_linhas('a1.txt', ['TED A 320,00 D', 'PIX B 100,00 C', 'TED C 320,00 C'])
        self.app.busca_var.set('32000')
        self.app.buscar_a1()
        self.app.update()
        self.assertTrue(self.app.tree_busca.winfo_ismapped())
        self.assertTrue(self.app.tree_deb.winfo_ismapped())
        self.assertEqual(len(self.app.tree_busca.get_children()), 2)
        self.assertEqual(len(self.app.tree_deb.get_children()), 2)
        self.assertEqual(self.app.var_falta.get(), '2')
        self.app.tree_busca.selection_set('1')
        self.app.update()
        self.assertEqual(self.app.tree_deb.selection(), ('1',))
        self.app.adicionar_e_comparar()
        self.app.update()
        self.assertEqual(self.app.busca_var.get(), '32000')
        self.assertEqual(self.app.abas.get(), 'Buscar e comparar')
        self.assertEqual(self.app.tree_busca.set('1', 'situacao'), '✓ no A2')
        self.assertEqual(self.app.tree_deb.set('1', 'situacao'), 'OK')
        self.assertEqual(self.app.tree_deb.set('0', 'situacao'), 'FALTA NO A2')
        self.assertEqual(self.app.tree_deb.selection(), ('1',))
        self.assertEqual(self.app.var_falta.get(), '1')
        with patch.object(main.webbrowser, 'open'):
            self.app.imprimir_relatorio()
        html = Path('No/relatorio_debitos.html').read_text(encoding='utf-8')
        self.assertIn('TED C 320,00 C', html)
        self.assertNotIn('PIX B 100,00 C', html)
        self.app.mostrar_todos()
        self.assertEqual(len(self.app.tree_busca.get_children()), 3)
        self.assertEqual(len(self.app.tree_deb.get_children()), 3)

    def test_selecao_da_comparacao_localiza_a_linha_original_no_a1(self):
        main.salvar_linhas('a1.txt', ['Saldo sem tipo', '', 'TED 25,00 D', 'PIX 50,00 C'])
        self.app.atualizar_tudo()
        self.app.update()
        self.app.tree_deb.selection_set('1')
        self.app.update()
        self.assertEqual(self.app.tree_busca.selection(), ('2',))
        self.assertEqual(self.app.tree_busca.set('2', 'linha'), '4')
        self.app.adicionar_e_comparar()
        self.app.update()
        self.assertEqual(main.carregar_linhas('a2.txt'), ['[4] PIX 50,00 C'])
        self.assertEqual(self.app.tree_deb.set('1', 'situacao'), 'OK')
        self.app.tipo_comparacao.set('Débitos')
        self.app.update()
        self.assertEqual(len(self.app.tree_busca.get_children()), 3)
        self.assertEqual(len(self.app.tree_deb.get_children()), 1)

    def test_selecao_mista_preserva_linhas_sem_dc_na_inclusao(self):
        main.salvar_linhas('a1.txt', ['Saldo sem tipo', 'TED 25,00 D', 'PIX 50,00 C'])
        self.app.atualizar_tudo()
        self.app.update()
        self.app.tree_busca.selection_set('0', '2')
        self.app.update()
        self.assertEqual(self.app.tree_busca.selection(), ('0', '2'))
        self.assertEqual(self.app.tree_deb.selection(), ('1',))
        self.app.adicionar_e_comparar()
        self.app.update()
        self.assertEqual(main.carregar_linhas('a2.txt'), ['[1] Saldo sem tipo', '[3] PIX 50,00 C'])



if __name__ == '__main__':
    unittest.main()
