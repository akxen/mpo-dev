FROM python:3.9-slim-buster

# Install Python packages
COPY requirements.txt /
RUN pip install -r requirements.txt

# Dependencies required to install GLPK
RUN apt-get update && apt-get install -y gcc musl-dev wget make gpg

# Download GLPK tarball and verify using signature
RUN mkdir /solver
WORKDIR /solver
RUN wget http://ftp.gnu.org/gnu/glpk/glpk-4.35.tar.gz \
    && wget ftp://ftp.gnu.org/gnu/glpk/glpk-4.35.tar.gz.sig \
    && gpg --keyserver keys.gnupg.net --recv-keys 5981E818

RUN  gpg --verify glpk-4.35.tar.gz.sig glpk-4.35.tar.gz

# Intall GLPK
RUN tar -xf glpk-4.35.tar.gz
WORKDIR /solver/glpk-4.35
RUN ./configure --disable-shared \
    && make \
    && make install \
    && make check \
    && make clean

# Remove packages to decrease image size
RUN apt-get --purge autoremove -y gcc musl-dev wget make gpg

# Copy project files into container
RUN mkdir /app
COPY ./project /app
WORKDIR /app

# Copy entrypoint script
RUN mkdir /scripts
COPY scripts/entrypoint.sh /scripts

CMD ["/scripts/entrypoint.sh"]
