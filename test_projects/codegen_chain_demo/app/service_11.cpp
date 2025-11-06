#include "service_11.h"

Service11::Service11() {}

void Service11::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service11::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
