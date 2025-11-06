#include "service_26.h"

Service26::Service26() {}

void Service26::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service26::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
