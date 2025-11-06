#include "service_33.h"

Service33::Service33() {}

void Service33::execute() {
    for (auto& cb : callbacks_) cb();
}

void Service33::registerCallback(std::function<void()> cb) {
    callbacks_.push_back(cb);
}
