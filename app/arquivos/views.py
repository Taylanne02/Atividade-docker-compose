from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ArquivoForm
from .models import Arquivo


def lista_arquivos(request):
    arquivos = Arquivo.objects.all().order_by("-enviado_em")

    if request.method == "POST":
        form = ArquivoForm(request.POST, request.FILES)

        if form.is_valid():
            arquivo = form.save()
            arquivo.nome = arquivo.arquivo.name.split("/")[-1]
            arquivo.save()
            messages.success(request, f"Arquivo '{arquivo.nome}' enviado com sucesso!")
            return redirect("lista_arquivos")
        else:
            messages.error(request, "Erro ao enviar arquivo. Verifique o formato e tente novamente.")
    else:
        form = ArquivoForm()

    return render(
        request,
        "arquivos/lista.html",
        {
            "form": form,
            "arquivos": arquivos,
        },
    )