#include "service_38.h"

Service38::Service38() {}

void Service38::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service38::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
