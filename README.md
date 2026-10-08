# Gerador de Polaroids — PrintHub Brasil (v2.0)

Monta folhas de impressão com fotos em moldura estilo Polaroid, prontas pra imprimir e cortar.

## Como usar
1. Coloque todas as fotos numa pasta (JPG, PNG, WEBP, BMP, TIFF).
2. Abra o programa e clique em **Escolher pasta…**. As fotos saem na ordem do nome.
3. Ajuste o que quiser — a prévia à direita mostra a folha exatamente como vai sair.
4. **Gerar PDF**.

## O que dá pra configurar
- **Folha**: A4, A3, A5, Carta, Ofício, 10×15, 13×18, 15×21, 20×25, 20×30, 30×40, SRA3,
  33×48, 40×60 ou qualquer medida; em pé ou deitada.
- **Margens** (cada lado separado ou todas iguais), **centralizar** e **espaço entre** as polaroids.
- **Polaroid**: modelos prontos (Clássica 8,8×10,7, Mini 5×7, Instax Mini, Square, Wide,
  10×12, 10×15) ou qualquer medida — largura, altura, borda dos lados, borda de cima e
  altura da foto. A base (onde vai a legenda) é o que sobra.
- **Na folha**: em pé, deitada ou automático (o que couber mais).
- **Cor da moldura** e contorno fino na foto.
- **Sangria**: a moldura passa do corte. Entre vizinhas ela nunca passa da metade do espaço.
- **Marcas de corte**: liga/desliga, comprimento, afastamento, espessura, cor; e linha fina
  em volta de cada polaroid.
- **Enquadramento**: centralizar no rosto, cortar pelo centro ou foto inteira.
- **Legenda**: sem legenda, o mesmo texto em todas ou o nome do arquivo; fonte (as instaladas
  no computador), tamanho (ou automático), cor, alinhamento, subir/descer.
- **Cópias** de cada foto, **resolução** (dpi) e **qualidade** do JPEG.
- **Perfis**: guarde configurações com nome e troque num clique.

Tudo fica salvo sozinho e volta na próxima abertura
(Windows: `%APPDATA%\PrintHub\Gerador de Polaroids`).

## Pra rodar pelo código (sem .exe)
Dois cliques em **ABRIR GERADOR.bat** (instala o que falta na primeira vez).
Precisa do Python de python.org — o da Microsoft Store vem sem o tkinter.

## Pra montar o .exe de distribuir
Dois cliques em **CONSTRUIR EXE.bat** num PC com Windows. Ele instala o PyInstaller, roda os
testes e só monta se eles passarem. O programa sai em `dist\GeradordePolaroids.exe`.

⚠ O OpenCV fica na série 4 (`requirements.txt`): a série 5 tirou o detector de rosto.

## Testes
- `python testes/rodar.py` — mede o PDF: folha, posições, sangria, marcas, janela da foto,
  legenda, giro, cópias, validações e o recorte pelo rosto.
- `python testes/interface.py` — abre a janela escondida e mexe como o usuário.

## Quando der problema
O registro fica em `%APPDATA%\PrintHub\Gerador de Polaroids\registro.txt`; cada erro gera
um `erro-<data>.txt` na mesma pasta. É esse arquivo que se manda pro suporte.

Criado por João Ebel — PrintHub Brasil.

## Licença
Código livre (licença MIT): pode usar, copiar, modificar e distribuir, inclusive
comercialmente — só mantenha o aviso de licença. Veja o arquivo `LICENSE`.
