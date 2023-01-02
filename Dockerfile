FROM python:3.10-bullseye
ENV PYTHONUNBUFFERED=1

RUN pip install -U pip                                                                          
RUN pip install poetry                                                                          
RUN mkdir /ayon
WORKDIR /ayon
COPY . .                                                                                        
RUN poetry config virtualenvs.create false \                                                    
  && poetry install --no-interaction --no-ansi                                                  

